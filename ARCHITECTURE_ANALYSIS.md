# MaratOS Architecture Analysis & Hardening Plan

**Analysis Date:** 2026-01-27
**Scope:** Backend architecture for agentic app-building with Kiro CLI as sole LLM access
**Environment:** Corporate deployment requiring durability, audit, and workspace sandboxing

---

## A) CURRENT STATE MAP

### A.1 Runtime Call Paths

#### Chat Request → LLM → Response

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ CHAT REQUEST FLOW                                                           │
└─────────────────────────────────────────────────────────────────────────────┘

1. HTTP Request
   POST /api/chat → app/api/chat.py:chat()
   ├── Validate ChatRequest (message, session_id?, agent_id?)
   ├── Rate limiting via slowapi
   └── Get/Create session in SQLite

2. Agent Resolution
   app/api/chat.py:321-337
   ├── agent_registry.get(agent_id) or get_default()
   └── Default: MOAgent (always)

3. Message History Loading
   app/api/chat.py:383-426
   ├── Load from messages table (sliding window: max 100)
   ├── Convert DBMessage → Message objects
   └── Add truncation notice if >100 messages

4. Pre-Processing (Before LLM)
   app/api/chat.py:428-576
   ├── Command parsing (/help, /project, etc.)
   ├── Project detection (autonomous mode trigger)
   ├── Auto-routing (regex patterns → spawn specialized agent)
   └── Memory context injection

5. LLM Execution
   app/agents/base.py:354-571 → Agent.chat()
   ├── Build system prompt + skill injection
   ├── Configure KiroConfig (model, trust_tools, timeout)
   └── Call kiro_provider.chat_completion_stream()

6. Kiro Provider Execution
   app/llm/kiro_provider.py:222-328
   ├── Spawn subprocess: kiro-cli chat --model X --trust-all-tools --no-interactive
   ├── Pipe formatted prompt to stdin
   ├── Collect stdout (kiro-cli doesn't truly stream)
   ├── Clean output (strip ANSI, banners, tool logs)
   └── Yield cleaned chunks with artificial 50-char chunking

7. Post-Processing (After LLM)
   app/api/chat.py:695-800
   ├── Parse [SPAWN:agent] markers → spawn subagents
   ├── Parse [CANVAS:type] markers → save artifacts
   ├── Parse mermaid blocks → create diagrams
   ├── Handle thinking blocks (__THINKING_START__, __THINKING_END__)
   └── Save assistant message to database

8. SSE Response
   StreamingResponse with events:
   - session_id, agent, model
   - thinking: true/false
   - model_thinking: true/false
   - content: "chunk"
   - orchestrating: true/false
   - subagent: {id, status, progress}
   - subagent_result: {agent, content}
   - canvas_create: {artifact}
   - [DONE]
```

#### Key Files in Chat Flow

| Step | File | Function |
|------|------|----------|
| Entry | `app/api/chat.py` | `chat()` |
| Agent Base | `app/agents/base.py` | `Agent.chat()` |
| LLM Provider | `app/llm/kiro_provider.py` | `chat_completion_stream()` |
| MO Agent | `app/agents/mo.py` | `MOAgent` |
| Registry | `app/agents/registry.py` | `agent_registry` |

---

### A.2 Agent Spawn Path

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ AGENT SPAWN FLOW ([SPAWN:agent] markers)                                    │
└─────────────────────────────────────────────────────────────────────────────┘

1. Detection
   app/api/chat.py:36
   SPAWN_PATTERN = r'\[SPAWN:(\w+)\]\s*(.+?)(?=\[SPAWN:|\Z)'

2. Parsing (during LLM response processing)
   app/api/chat.py:750-800
   ├── Extract agent_id and task_description
   ├── Create SubagentTask via subagent_manager.spawn()
   └── Emit subagent SSE events

3. Task Execution
   app/subagents/runner.py:SubagentRunner.run_task()
   ├── Get agent from registry
   ├── Build context with task description
   ├── Call agent.chat() (same path as main chat)
   └── Parse goals/checkpoints from response

4. Progress Tracking
   app/subagents/manager.py:SubagentTask
   ├── Goals: [GOAL:1], [GOAL_DONE:1], [GOAL_FAILED:1]
   ├── Checkpoints: [CHECKPOINT:name]
   └── Status: PENDING → SPAWNING → RUNNING → COMPLETED/FAILED

5. Inter-Agent Communication
   app/subagents/runner.py:parse_agent_requests()
   ├── [REQUEST:reviewer] text → spawn reviewer
   ├── [REVIEW_REQUEST] text → shorthand for reviewer
   └── Nested spawning with dependency tracking
```

#### Key Files in Spawn Flow

| Component | File | Purpose |
|-----------|------|---------|
| Manager | `app/subagents/manager.py` | Task lifecycle, status tracking |
| Runner | `app/subagents/runner.py` | Execute tasks, parse markers |
| Metrics | `app/subagents/metrics.py` | Performance tracking |
| Recovery | `app/subagents/recovery.py` | Failure handling (stub) |

---

### A.3 Skills Execution Path

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ SKILLS FLOW                                                                 │
└─────────────────────────────────────────────────────────────────────────────┘

1. Loading (Application Startup)
   app/main.py:lifespan()
   └── load_all_skills() from ~/.maratos/skills/ and app/skills/

2. Skill Definition
   YAML files with:
   ├── triggers: ["keyword1", "keyword2"]
   ├── workflow: [{action: kiro_architect, params: {...}}, ...]
   ├── system_context: "additional prompt text"
   ├── quality_checklist: ["item1", "item2"]
   └── test_requirements: ["test1", "test2"]

3. Auto-Selection (Implicit)
   app/agents/base.py:get_system_prompt()
   ├── skill_registry.find_by_trigger(user_message)
   ├── Match skills based on trigger keywords
   └── Inject skill context into system prompt

4. Execution (If workflow defined)
   app/skills/executor.py:SkillExecutor
   ├── Iterate workflow steps
   ├── Route actions: kiro_architect, kiro_validate, kiro_test, shell, filesystem
   └── Collect results

5. **CRITICAL GAP**: Skills are context-only, not execution-based
   - Workflows exist but are rarely invoked
   - Skills primarily inject context into prompts
   - No structured execution pipeline
```

#### Key Files in Skills Flow

| Component | File | Purpose |
|-----------|------|---------|
| Base | `app/skills/base.py` | Skill, SkillRegistry dataclasses |
| Loader | `app/skills/loader.py` | YAML parsing, validation |
| Executor | `app/skills/executor.py` | Workflow execution (underused) |
| API | `app/api/skills.py` | REST endpoints |

---

### A.4 Tools Execution Path

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TOOLS FLOW - **CRITICAL ARCHITECTURE ISSUE**                                │
└─────────────────────────────────────────────────────────────────────────────┘

There are TWO PARALLEL tool systems that DON'T INTEGRATE:

═══════════════════════════════════════════════════════════════════════════════
PATH A: MaratOS Tools (DEFINED but NOT USED by standard agents)
═══════════════════════════════════════════════════════════════════════════════

1. Tool Definition
   app/tools/*.py → Tool subclasses with execute() methods
   ├── FilesystemTool: read, write, list, copy, delete
   ├── ShellTool: bash command execution
   ├── KiroTool: validate, test, prompt actions
   ├── WebSearchTool, WebFetchTool
   ├── SessionsTool: cross-session history
   ├── CanvasTool: visual artifacts
   └── RoutingTool: routing validation

2. Registration
   app/tools/*.py → Each registers with registry.register(Tool())

3. Schema Generation
   app/tools/base.py:Tool.to_schema() → JSON schema for LLM function calling

4. Execution Point
   app/agents/base.py:576
   async def run_tool(tool_id, **kwargs) -> ToolResult:
       return await tool_registry.execute(tool_id, **kwargs)

5. **PROBLEM**: run_tool() is NEVER CALLED by standard agents!
   - MOAgent, CoderAgent, etc. don't invoke tools directly
   - They rely on kiro-cli's built-in tools

═══════════════════════════════════════════════════════════════════════════════
PATH B: Kiro-CLI Built-in Tools (ACTUALLY USED)
═══════════════════════════════════════════════════════════════════════════════

1. Kiro-CLI has its own tool system:
   - filesystem operations (read, write, list)
   - shell command execution
   - web fetch/search

2. When agent calls kiro_provider.chat_completion_stream():
   - Prompt sent to kiro-cli subprocess
   - Kiro-CLI decides tool calls internally
   - Tool output appears in stdout
   - MaratOS only sees the final text response

3. **NO CONTROL** over:
   - What files kiro-cli reads/writes
   - What commands it executes
   - Workspace sandboxing
   - Audit logging

═══════════════════════════════════════════════════════════════════════════════
PATH C: KiroAgent (ALTERNATIVE that does use MaratOS tools)
═══════════════════════════════════════════════════════════════════════════════

app/agents/kiro.py:KiroAgent
├── Parses <tool_code>{json}</tool_code> blocks from LLM output
├── Extracts tool name and params
├── Calls tool_registry.execute(tool_name, **params)
└── Yields tool results to user

**BUT**: KiroAgent is NOT the default agent.
Standard agents (MO, Coder, etc.) don't use this mechanism.
```

#### Tools Architecture Diagram

```
                    CURRENT STATE (BROKEN)
                    ═════════════════════

   ┌─────────────────┐         ┌─────────────────┐
   │  MaratOS Tools  │         │  Kiro-CLI Tools │
   │  (app/tools/)   │         │  (built-in)     │
   ├─────────────────┤         ├─────────────────┤
   │ FilesystemTool  │         │ fs read/write   │
   │ ShellTool       │         │ bash exec       │
   │ KiroTool        │         │ web fetch       │
   │ RoutingTool     │         │ etc.            │
   └────────┬────────┘         └────────┬────────┘
            │                           │
            │ NOT USED                  │ ACTUALLY USED
            │                           │
            ▼                           ▼
   ┌─────────────────┐         ┌─────────────────┐
   │  KiroAgent      │         │  Standard Agents│
   │  (unused)       │         │  MO, Coder, etc.│
   └─────────────────┘         └────────┬────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │  kiro-cli       │
                               │  subprocess     │
                               │  (black box)    │
                               └─────────────────┘
```

---

### A.5 Project Registry/Analyzer Path

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ AUTONOMOUS PROJECT FLOW                                                     │
└─────────────────────────────────────────────────────────────────────────────┘

1. Detection
   app/autonomous/detection.py:ProjectDetector.detect()
   ├── Analyze message for complexity signals
   └── Return DetectionResult(should_project, reason, complexity)

2. Planning Phase
   app/autonomous/inline_orchestrator.py:InlineOrchestrator.detect_and_plan()
   ├── Create ProjectPlan
   ├── Spawn architect to break down tasks
   └── Yield plan_ready event with tasks

3. Approval Gate
   User responds: "approve", "start", "yes" → proceed
   User responds: "cancel", "no" → abort
   Other response → treat as adjustment

4. Execution Phase
   app/autonomous/orchestrator.py:Orchestrator.start()
   ├── For each task (respecting depends_on):
   │   ├── Spawn appropriate agent
   │   ├── Execute task
   │   ├── Run quality gates (tests, lint, review)
   │   └── Retry on failure (max_attempts)
   └── Yield progress events

5. Git Operations
   app/autonomous/git_ops.py
   ├── Commit changes
   ├── Push to remote
   └── Create PR (if configured)

6. State Persistence
   app/database.py: AutonomousProject, AutonomousTask tables
   **GAP**: No checkpoint/recovery mechanism
```

---

## B) GAPS (TOP 10)

### GAP 1: Tools Are Defined But Not Used

**Impact:** CRITICAL - Security, audit, sandboxing impossible
**Evidence:**
- `app/tools/*.py` defines 8 tools with execute() methods
- `app/agents/base.py:576` has `run_tool()` but it's never called
- `app/llm/kiro_provider.py` sends prompts to kiro-cli which uses its own tools

**Quick Fix:** N/A - Requires architecture change
**Proper Fix:** Intercept kiro-cli output, execute tools via MaratOS registry

---

### GAP 2: No Workspace Sandboxing Enforcement

**Impact:** HIGH - Arbitrary file writes possible
**Evidence:**
- `app/tools/filesystem.py:30-50` defines ALLOWED_WRITE_PATHS
- BUT kiro-cli ignores this and writes wherever its tools decide
- No runtime enforcement

**Quick Fix:** Chroot/container isolation
**Proper Fix:** Implement MaratOS tool execution with sandbox checks

---

### GAP 3: No Audit Logging

**Impact:** HIGH - Cannot track what agents did
**Evidence:**
- No logging of tool executions
- No logging of file modifications
- No logging of shell commands
- Only sparse `logger.info()` calls

**Quick Fix:** Add logging middleware
**Proper Fix:** Structured audit log with tool calls, file changes, outcomes

---

### GAP 4: Tasks Not Restart-Safe (No Durability)

**Impact:** HIGH - Lost work on restart
**Evidence:**
- `app/subagents/manager.py` stores tasks in memory only
- `SubagentTask` not persisted to database
- `app/autonomous/orchestrator.py` has no checkpoint recovery
- `app/subagents/recovery.py` exists but is stub only

**Quick Fix:** Serialize task state to JSON file
**Proper Fix:** Persist SubagentTask to database, implement recovery

---

### GAP 5: Kiro-CLI Output Parsing Is Fragile

**Impact:** MEDIUM - Missed content, false positives
**Evidence:**
- `app/llm/kiro_provider.py:95-157` has complex regex-based cleaning
- `app/agents/kiro.py:17-51` has another set of filter patterns
- No formal grammar for kiro-cli output

**Quick Fix:** More comprehensive regex patterns
**Proper Fix:** Request structured output format from kiro-cli

---

### GAP 6: Skills System Underutilized

**Impact:** MEDIUM - Lost quality enforcement
**Evidence:**
- `app/skills/executor.py` exists but rarely invoked
- Skills only inject context, don't enforce workflows
- `quality_checklist` and `test_requirements` ignored

**Quick Fix:** Call executor after agent response
**Proper Fix:** Integrate skills into agent execution loop

---

### GAP 7: No Rate Limiting on Subagent Spawning

**Impact:** MEDIUM - Resource exhaustion possible
**Evidence:**
- `app/api/chat.py` has rate limiting on chat endpoint
- `app/subagents/manager.py` has no spawn limits
- Recursive spawning via [SPAWN:] unlimited

**Quick Fix:** Add max concurrent subagents setting
**Proper Fix:** Token bucket rate limiter on spawn

---

### GAP 8: Memory System Optional and Fragile

**Impact:** LOW - Degraded experience without memory
**Evidence:**
- `app/api/chat.py:664-685` wraps memory in try/except with pass
- Multiple exception types caught silently
- No fallback behavior

**Quick Fix:** Log all memory errors
**Proper Fix:** Memory as required component with health checks

---

### GAP 9: No Agent Execution Timeout

**Impact:** MEDIUM - Hung requests possible
**Evidence:**
- `app/llm/kiro_provider.py:24` has `timeout: int = 300`
- BUT `app/agents/base.py` doesn't enforce timeouts
- Long-running kiro-cli calls block forever

**Quick Fix:** asyncio.timeout() wrapper
**Proper Fix:** Circuit breaker pattern with graceful degradation

---

### GAP 10: Routing Tool Not Enforced

**Impact:** LOW - Can bypass routing validation
**Evidence:**
- `app/tools/routing.py` validates routing decisions
- MO's prompt says "MANDATORY" but not enforced
- Agent can ignore tool and spawn directly

**Quick Fix:** N/A - LLM behavior
**Proper Fix:** Parse response, block invalid spawns

---

## C) PHASE PLAN

### Phase 1: Observability & Audit

**Objectives:**
- Add structured audit logging
- Track all tool executions (even kiro-cli's)
- Enable post-hoc analysis

**Touched Files:**
| File | Changes |
|------|---------|
| `app/audit/__init__.py` | NEW: Module init |
| `app/audit/logger.py` | NEW: AuditLogger class |
| `app/audit/models.py` | NEW: AuditEvent dataclass |
| `app/llm/kiro_provider.py` | Add audit hooks before/after calls |
| `app/api/chat.py` | Log request/response events |
| `app/subagents/runner.py` | Log spawn/complete events |

**New Modules:**
```
app/audit/
├── __init__.py
├── logger.py      # AuditLogger with file/db backends
├── models.py      # AuditEvent, AuditCategory enums
└── middleware.py  # FastAPI middleware for request logging
```

**Risks:**
- Performance overhead from logging
- Log file growth

**Test Gates:**
- [ ] All chat requests logged with session_id
- [ ] All agent spawns logged with parent_id
- [ ] All kiro-cli invocations logged with prompt hash
- [ ] Logs queryable by session_id

---

### Phase 2: Task Durability

**Objectives:**
- Persist subagent tasks to database
- Enable restart recovery
- Track task history

**Touched Files:**
| File | Changes |
|------|---------|
| `app/database.py` | Add SubagentTask table |
| `app/subagents/manager.py` | Add DB persistence |
| `app/subagents/recovery.py` | Implement recovery logic |
| `app/main.py` | Add recovery on startup |
| `app/api/subagents.py` | Add history endpoint |

**New Tables:**
```sql
CREATE TABLE subagent_tasks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    parent_task_id TEXT,
    agent_id TEXT NOT NULL,
    task TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT,
    error TEXT,
    goals JSON,
    checkpoints JSON,
    created_at DATETIME,
    started_at DATETIME,
    completed_at DATETIME
);
```

**Risks:**
- Migration for existing deployments
- Orphaned tasks on crash

**Test Gates:**
- [ ] Task survives server restart
- [ ] Incomplete tasks resume on startup
- [ ] Task history queryable via API
- [ ] Parent-child relationships preserved

---

### Phase 3: Tool Execution Interception

**Objectives:**
- Execute tools via MaratOS registry
- Enforce workspace sandboxing
- Enable audit of tool calls

**Touched Files:**
| File | Changes |
|------|---------|
| `app/agents/base.py` | Add tool interception layer |
| `app/agents/tool_executor.py` | NEW: Tool execution orchestrator |
| `app/llm/kiro_provider.py` | Extract tool call markers |
| `app/tools/base.py` | Add pre/post hooks |
| `app/tools/filesystem.py` | Enforce sandbox |

**New Module:**
```
app/agents/tool_executor.py
├── ToolExecutor class
├── parse_tool_calls() from kiro output
├── execute_with_sandbox()
└── format_tool_results()
```

**Architecture Change:**
```
BEFORE:
Agent → kiro_provider → kiro-cli (tools executed internally)

AFTER:
Agent → kiro_provider → kiro-cli (tool calls extracted)
                      ↓
                 ToolExecutor
                      ↓
              tool_registry.execute() (sandboxed)
                      ↓
              Results injected back to context
```

**Risks:**
- Breaking change to agent behavior
- Tool result format mismatch
- Latency increase

**Test Gates:**
- [ ] FilesystemTool.write() blocked outside workspace
- [ ] ShellTool commands logged to audit
- [ ] Tool results visible in response
- [ ] Existing agent prompts still work

---

### Phase 4: Skill Workflow Enforcement

**Objectives:**
- Execute skill workflows after agent response
- Enforce quality checklists
- Run test requirements

**Touched Files:**
| File | Changes |
|------|---------|
| `app/skills/executor.py` | Full implementation |
| `app/skills/validator.py` | NEW: Checklist validation |
| `app/agents/base.py` | Call skill workflow post-response |
| `app/api/chat.py` | Yield skill execution events |

**New Module:**
```
app/skills/validator.py
├── validate_checklist(response, checklist)
├── run_tests(workspace, requirements)
└── aggregate_results()
```

**Risks:**
- Increased response latency
- Overly strict validation blocking valid work

**Test Gates:**
- [ ] Skill workflow executes after agent response
- [ ] Failed checklist items reported to user
- [ ] Test requirements executed if files modified
- [ ] Validation can be bypassed with flag

---

### Phase 5: Rate Limiting & Circuit Breakers

**Objectives:**
- Prevent resource exhaustion
- Handle kiro-cli failures gracefully
- Set timeouts on all operations

**Touched Files:**
| File | Changes |
|------|---------|
| `app/subagents/manager.py` | Add spawn rate limiter |
| `app/agents/base.py` | Add timeout wrapper |
| `app/llm/kiro_provider.py` | Add circuit breaker |
| `app/config.py` | Add rate limit settings |

**New Settings:**
```python
max_concurrent_subagents: int = 5
subagent_spawn_rate: str = "10/minute"
agent_timeout_seconds: int = 300
circuit_breaker_threshold: int = 3
circuit_breaker_reset_seconds: int = 60
```

**Risks:**
- Legitimate work blocked by limits
- Tuning required per environment

**Test Gates:**
- [ ] 6th concurrent subagent rejected
- [ ] Agent times out after 300s
- [ ] Circuit breaker trips after 3 failures
- [ ] Circuit breaker resets after 60s

---

## D) ACCEPTANCE CRITERIA

### Phase 1: Observability & Audit
| Criterion | Measurement |
|-----------|-------------|
| Audit log coverage | 100% of chat requests logged |
| Log queryability | Can retrieve all events for session within 1s |
| No data loss | Logs survive server restart |
| Performance impact | <50ms added latency per request |

### Phase 2: Task Durability
| Criterion | Measurement |
|-----------|-------------|
| Persistence coverage | 100% of tasks in database |
| Recovery success | >95% of interrupted tasks resume |
| History retention | 30 days of task history |
| Query performance | <500ms for task history by session |

### Phase 3: Tool Execution Interception
| Criterion | Measurement |
|-----------|-------------|
| Sandbox enforcement | 100% of writes blocked outside workspace |
| Tool audit coverage | 100% of tool calls logged |
| Functional parity | All existing agent behaviors preserved |
| Latency impact | <200ms added per tool call |

### Phase 4: Skill Workflow Enforcement
| Criterion | Measurement |
|-----------|-------------|
| Workflow execution | 100% of matched skills execute workflow |
| Checklist validation | All checklist items evaluated |
| Test execution | Tests run when code files modified |
| Override support | Flag to bypass validation works |

### Phase 5: Rate Limiting & Circuit Breakers
| Criterion | Measurement |
|-----------|-------------|
| Rate limit enforcement | Excess requests rejected with 429 |
| Timeout enforcement | All operations complete or timeout |
| Circuit breaker trips | After configured threshold |
| Graceful degradation | Informative error messages |

---

## Summary

**Critical Finding:** The MaratOS tools system is architecturally disconnected from actual execution. Kiro-CLI acts as a black box that executes its own tools, bypassing all MaratOS security, auditing, and sandboxing.

**Recommended Priority:**
1. Phase 1 (Audit) - Immediate visibility
2. Phase 3 (Tool Interception) - Security enforcement
3. Phase 2 (Durability) - Reliability
4. Phase 5 (Rate Limits) - Stability
5. Phase 4 (Skills) - Quality

**Estimated Effort:** 4-6 weeks for full implementation with proper testing.

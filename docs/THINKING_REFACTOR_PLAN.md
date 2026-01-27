# Thinking Mode Refactor Plan

## Overview
Comprehensive refactor of the thinking system to make it more structured, adaptive, and measurable.

## Current State
- Thinking levels: off/minimal/low/medium/high/max (config.py)
- XML-style tags: `<thinking>...</thinking>` parsed via regex
- Global thinking level setting (not context-aware)
- Thinking content stripped from display, not persisted
- No metrics or feedback loop

## Implementation Phases

### Phase 1: Foundation - Structured Thinking Module
**Files to create:**
- `backend/app/thinking/__init__.py`
- `backend/app/thinking/models.py` - Data models for thinking
- `backend/app/thinking/manager.py` - Core thinking manager
- `backend/app/thinking/templates.py` - Task-specific thinking templates
- `backend/app/thinking/metrics.py` - Thinking metrics tracking

**Key changes:**
1. Replace XML tags with structured JSON format
2. Create ThinkingBlock, ThinkingStep, ThinkingSession models
3. Implement ThinkingManager class

### Phase 2: Persistence & Storage
**Changes:**
- Add thinking_data column to chat messages table
- Store thinking blocks with metadata
- Enable retrieval of thinking history

### Phase 3: Adaptive Thinking
**Changes:**
- Implement AdaptiveThinkingManager
- Context-aware level selection based on:
  - Task complexity (code analysis, simple query, etc.)
  - Message length/structure
  - Error history
  - User preferences

### Phase 4: Thinking Templates
**Templates for:**
- `code_review`: security, performance, maintainability
- `architecture`: scalability, trade-offs, implementation
- `debugging`: root cause, reproduction, fix validation
- `general`: analysis, evaluation, decision

### Phase 5: Agent Integration
**Changes:**
- Standardize thinking integration across ALL agents
- Each agent uses ThinkingManager
- Consistent thinking output format

### Phase 6: Metrics & Feedback
**Metrics to track:**
- Thinking duration per level
- Token usage per thinking level
- Task success correlation
- User satisfaction signals

### Phase 7: Frontend Updates
**Changes:**
- Update SSE event handling for new format
- Display thinking steps (collapsible)
- Show thinking metrics
- Thinking history view

---

## Data Models

```python
# ThinkingStep
{
    "id": "uuid",
    "type": "analysis|evaluation|decision|validation",
    "content": "...",
    "duration_ms": 150,
    "tokens": 50
}

# ThinkingBlock
{
    "id": "uuid",
    "level": "medium",
    "template": "code_review",
    "steps": [ThinkingStep, ...],
    "total_duration_ms": 1500,
    "total_tokens": 200,
    "started_at": "ISO timestamp",
    "completed_at": "ISO timestamp"
}

# ThinkingSession (per message)
{
    "message_id": "uuid",
    "blocks": [ThinkingBlock, ...],
    "adaptive_level_used": "high",
    "original_level": "medium",
    "complexity_score": 0.75
}
```

## Implementation Order

1. [x] Create thinking module structure
2. [ ] Implement models (ThinkingStep, ThinkingBlock, ThinkingSession)
3. [ ] Implement ThinkingManager
4. [ ] Implement ThinkingTemplates
5. [ ] Implement AdaptiveThinkingManager
6. [ ] Implement ThinkingMetrics
7. [ ] Update base agent to use ThinkingManager
8. [ ] Update chat.py for new streaming format
9. [ ] Add database migrations for persistence
10. [ ] Update frontend stores
11. [ ] Update frontend components
12. [ ] Add tests

## Migration Strategy
- Keep backward compatibility with old XML tags during transition
- New format: JSON-based thinking events
- Frontend handles both formats initially

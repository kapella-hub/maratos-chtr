"""Chat API endpoints."""

import json
import re
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import agent_registry
from app.config import settings

# Rate limiter for chat endpoint
limiter = Limiter(key_func=get_remote_address, enabled=settings.rate_limit_enabled)
from app.agents.base import Message, convert_numbered_lines_to_codeblock
from app.commands import command_registry
from app.database import Message as DBMessage
from app.database import Session as DBSession
from app.database import get_db
from app.subagents.runner import subagent_runner
from app.subagents.manager import subagent_manager, TaskStatus

logger = logging.getLogger(__name__)

# Pattern to match [SPAWN:agent_id] task description
SPAWN_PATTERN = re.compile(r'\[SPAWN:(\w+)\]\s*(.+?)(?=\[SPAWN:|\Z)', re.DOTALL)

# Auto-routing patterns - detect user intent and route to appropriate agent
AUTO_ROUTE_PATTERNS = [
    (re.compile(r'\b(analyze|review|audit|examine)\b.*\b(code|codebase|project|directory|file)', re.I), 'reviewer'),
    (re.compile(r'\b(implement|build|create|fix|add|update)\b.*\b(feature|function|bug|code)', re.I), 'coder'),
    (re.compile(r'\b(design|architect)\b.*\b(system|api|architecture)', re.I), 'architect'),
    (re.compile(r'\b(write|generate|create)\b.*\b(test|tests|spec)', re.I), 'tester'),
    (re.compile(r'\b(write|create|update)\b.*\b(doc|documentation|readme)', re.I), 'docs'),
    (re.compile(r'\b(deploy|docker|ci|cd|pipeline|kubernetes|k8s)\b', re.I), 'devops'),
]


def detect_auto_route(message: str) -> tuple[str | None, str]:
    """Detect if message should be auto-routed to a specific agent.

    Returns (agent_id, task_description) or (None, "") if no match.
    """
    for pattern, agent_id in AUTO_ROUTE_PATTERNS:
        if pattern.search(message):
            return agent_id, message
    return None, ""

# Pattern to match [CANVAS:type attr="value"] content [/CANVAS]
CANVAS_PATTERN = re.compile(
    r'\[CANVAS:(\w+)([^\]]*)\](.*?)\[/CANVAS\]',
    re.DOTALL
)


def parse_canvas_attrs(attr_string: str) -> dict[str, str]:
    """Parse attributes from canvas marker like title="..." lang="..."."""
    attrs = {}
    # Match attr="value" or attr='value'
    attr_pattern = re.compile(r'(\w+)=["\']([^"\']*)["\']')
    for match in attr_pattern.finditer(attr_string):
        attrs[match.group(1)] = match.group(2)
    return attrs


async def process_canvas_markers(
    content: str,
    session_id: str,
    message_id: str,
) -> list[dict[str, Any]]:
    """Parse and save canvas artifacts from response content.

    Returns list of artifact data for SSE events.
    """
    from app.database import CanvasArtifact, async_session_factory

    artifacts = []
    matches = CANVAS_PATTERN.findall(content)

    if not matches:
        return artifacts

    async with async_session_factory() as db:
        for artifact_type, attr_string, artifact_content in matches:
            attrs = parse_canvas_attrs(attr_string)

            title = attrs.get("title", f"Untitled {artifact_type}")
            language = attrs.get("lang") or attrs.get("language")
            editable = attrs.get("editable", "").lower() == "true"

            metadata = {}
            if language:
                metadata["language"] = language
            if editable:
                metadata["editable"] = True

            artifact = CanvasArtifact(
                id=str(uuid.uuid4()),
                session_id=session_id,
                message_id=message_id,
                artifact_type=artifact_type.lower(),
                title=title,
                content=artifact_content.strip(),
                extra_data=metadata if metadata else None,
            )

            db.add(artifact)

            artifacts.append({
                "id": artifact.id,
                "type": artifact_type.lower(),
                "title": title,
                "content": artifact_content.strip(),
                "metadata": metadata,
            })

        await db.commit()

    return artifacts


# Pattern to match mermaid code blocks: ```mermaid ... ```
MERMAID_PATTERN = re.compile(
    r'```mermaid\s*\n(.*?)\n```',
    re.DOTALL | re.IGNORECASE
)


async def process_mermaid_blocks(
    content: str,
    session_id: str,
    message_id: str,
) -> list[dict[str, Any]]:
    """Detect mermaid code blocks and create canvas artifacts.

    This enables canvas support for kiro-cli which outputs mermaid as code blocks.
    Returns list of artifact data for SSE events.
    """
    from app.database import CanvasArtifact, async_session_factory

    artifacts = []
    matches = MERMAID_PATTERN.findall(content)

    if not matches:
        return artifacts

    async with async_session_factory() as db:
        for i, mermaid_content in enumerate(matches):
            # Generate a title from the first line or type of diagram
            first_line = mermaid_content.strip().split('\n')[0]
            if first_line.startswith('flowchart'):
                title = "Flowchart"
            elif first_line.startswith('sequenceDiagram'):
                title = "Sequence Diagram"
            elif first_line.startswith('classDiagram'):
                title = "Class Diagram"
            elif first_line.startswith('erDiagram'):
                title = "ER Diagram"
            elif first_line.startswith('gantt'):
                title = "Gantt Chart"
            elif first_line.startswith('pie'):
                title = "Pie Chart"
            elif first_line.startswith('graph'):
                title = "Graph"
            else:
                title = f"Diagram {i + 1}" if i > 0 else "Diagram"

            artifact = CanvasArtifact(
                id=str(uuid.uuid4()),
                session_id=session_id,
                message_id=message_id,
                artifact_type="diagram",
                title=title,
                content=mermaid_content.strip(),
                extra_data=None,
            )

            db.add(artifact)

            artifacts.append({
                "id": artifact.id,
                "type": "diagram",
                "title": title,
                "content": mermaid_content.strip(),
                "metadata": None,
            })

        await db.commit()

    return artifacts


def clean_cli_output(text: str) -> str:
    """Remove CLI artifacts like ASCII banners, spinners, and verbose log lines."""
    if not text:
        return text

    lines = text.split('\n')
    cleaned = []
    skip_until_empty = False

    for line in lines:
        # Skip ASCII art banner lines (contain lots of Unicode box/block chars)
        special_count = sum(1 for c in line if c in '⠀▀▄█░▒▓│╭╮╯╰─┌┐└┘├┤┬┴┼⣴⣶⣦⣿⢰⢸⠈⠙⠁⠀')
        if special_count > len(line) * 0.3 and len(line) > 10:
            continue

        # Skip "Did you know?" banners and similar
        if 'Did you know?' in line or '─────' in line:
            skip_until_empty = True
            continue
        if skip_until_empty:
            if not line.strip():
                skip_until_empty = False
            continue

        # Skip model selection lines
        if line.strip().startswith('Model:') and ('Auto' in line or 'claude' in line):
            continue

        # Skip tool approval errors
        if 'Tool approval required' in line or '--trust-all-tools' in line:
            continue

        # Skip verbose operation summaries
        if re.match(r'^\s*Summary:\s*\d+\s*operations?', line):
            continue
        if re.match(r'^\s*\d+\s*operations?\s+processed', line):
            continue

        cleaned.append(line)

    # Remove leading/trailing empty lines and collapse multiple empty lines
    result = '\n'.join(cleaned)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


async def generate_title(user_message: str, assistant_response: str) -> str:
    """Generate a concise title for the chat session."""
    import litellm
    from app.config import settings
    
    try:
        response = await litellm.acompletion(
            model=settings.default_model,
            messages=[
                {
                    "role": "system",
                    "content": "Generate a brief, descriptive title (max 50 chars) for this conversation. Return ONLY the title, no quotes or explanation."
                },
                {
                    "role": "user", 
                    "content": f"User: {user_message[:500]}\n\nAssistant: {assistant_response[:500]}"
                }
            ],
            max_tokens=60,
            temperature=0.3,
        )
        title = response.choices[0].message.content.strip()
        # Clean up any quotes
        title = title.strip('"\'')
        return title[:100]  # Safety limit
    except Exception as e:
        logger.warning(f"Failed to generate title: {e}")
        # Fallback to simple extraction
        return user_message[:50].split('\n')[0] + "..." if len(user_message) > 50 else user_message.split('\n')[0]

router = APIRouter(prefix="/chat")


class ChatRequest(BaseModel):
    """Chat request body."""

    message: str = Field(min_length=1, max_length=50000)
    session_id: str | None = None
    agent_id: str | None = None  # Optional: specify agent (mo, architect, reviewer)
    context: dict[str, Any] | None = None

    # Inline project control
    project_action: str | None = None  # approve, adjust, pause, resume, cancel
    project_adjustments: dict[str, Any] | None = None  # For adjust action

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        """Validate message is not empty or whitespace only."""
        if not v.strip():
            raise ValueError("Message cannot be empty or whitespace only")
        return v


class SessionResponse(BaseModel):
    """Session response."""

    id: str
    agent_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    """Message response."""

    id: str
    role: str
    content: str
    created_at: datetime


@router.post("")
@limiter.limit(settings.rate_limit_chat)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Send a message and stream the response."""
    # Get agent (use specified or registry default)
    if chat_request.agent_id:
        agent = agent_registry.get(chat_request.agent_id)
        agent_id = chat_request.agent_id
    else:
        agent = agent_registry.get_default()
        agent_id = agent.id if agent else "mo"
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    # Get or create session
    try:
        if chat_request.session_id:
            result = await db.execute(
                select(DBSession).where(DBSession.id == chat_request.session_id)
            )
            session = result.scalar_one_or_none()
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            # Update agent if changed
            if session.agent_id != agent_id:
                session.agent_id = agent_id
                await db.commit()
        else:
            session = DBSession(
                id=str(uuid.uuid4()),
                agent_id=agent_id,
                title=chat_request.message[:100] if chat_request.message else None,
            )
            db.add(session)
            await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Database integrity error creating session: {e}")
        raise HTTPException(status_code=409, detail="Session conflict - please try again")
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error creating session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error")

    # Set current session for cross-session and canvas tools
    try:
        from app.tools.sessions import sessions_tool
        sessions_tool.set_current_session(session.id)
    except ImportError:
        pass  # Sessions tool not available

    try:
        from app.tools.canvas import canvas_tool
        canvas_tool.set_session(session.id)
    except ImportError:
        pass  # Canvas tool not available

    # Load conversation history with pagination to prevent OOM
    # First, count total messages
    count_result = await db.execute(
        select(func.count(DBMessage.id)).where(DBMessage.session_id == session.id)
    )
    total_messages = count_result.scalar() or 0

    # Load only recent messages (sliding window)
    max_messages = settings.max_history_messages
    messages: list[Message] = []

    if total_messages > max_messages:
        # Get count of older messages that will be summarized
        older_count = total_messages - max_messages
        logger.info(f"Session {session.id}: {total_messages} messages, loading last {max_messages}")

        # Add a system message about truncated history
        messages.append(Message(
            role="system",
            content=f"[Note: This conversation has {total_messages} messages. Showing the most recent {max_messages}. {older_count} earlier messages were summarized.]"
        ))

        # Load only recent messages
        result = await db.execute(
            select(DBMessage)
            .where(DBMessage.session_id == session.id)
            .order_by(DBMessage.created_at.desc())
            .limit(max_messages)
        )
        db_messages = list(reversed(result.scalars().all()))  # Reverse to chronological order
    else:
        # Load all messages (small conversation)
        result = await db.execute(
            select(DBMessage)
            .where(DBMessage.session_id == session.id)
            .order_by(DBMessage.created_at)
        )
        db_messages = result.scalars().all()

    # Convert to Message objects
    messages.extend([
        Message(role=m.role, content=m.content, tool_calls=m.tool_calls)
        for m in db_messages
    ])

    # Check for slash commands
    actual_message = chat_request.message
    project_context = None
    command_response = None

    command, args = command_registry.parse(chat_request.message)
    if command:
        logger.info(f"Processing command: /{command.name} {args[:50]}...")
        context = chat_request.context or {}
        result = command.handler(args, context)

        if "error" in result:
            # Command failed - return error as message
            command_response = f"**Error:** {result['error']}"
            if "example" in result:
                command_response += f"\n\n**Example:** `{result['example']}`"
            if "available" in result:
                command_response += f"\n\n**Available:** {', '.join(result['available'])}"

        elif "message" in result:
            # Command has a direct message response (like /help or /project list)
            command_response = result["message"]

        elif "expanded_prompt" in result:
            # Command expands to a full prompt
            actual_message = result["expanded_prompt"]
            if "agent_id" in result:
                new_agent = agent_registry.get(result["agent_id"])
                if new_agent:
                    agent = new_agent
                    agent_id = result["agent_id"]

        if "project_context" in result:
            project_context = result["project_context"]

    # Add user message (original or expanded)
    user_message = Message(role="user", content=actual_message)
    messages.append(user_message)

    # Save user message
    try:
        db_user_msg = DBMessage(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role="user",
            content=chat_request.message,
        )
        db.add(db_user_msg)
        await db.commit()
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error saving user message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save message")

    async def generate():
        """Generate streaming response."""
        full_response = ""

        # Yield session ID, agent info, and current model first
        from app.config import settings
        current_model = settings.default_model or "claude-sonnet-4.5"
        yield f"data: {{\"session_id\": \"{session.id}\", \"agent\": \"{agent_id}\", \"model\": \"{current_model}\"}}\n\n"

        # Handle inline project actions (approve, pause, cancel, etc.)
        if chat_request.project_action:
            from app.autonomous.inline_orchestrator import handle_project_action
            try:
                async for event in handle_project_action(
                    session_id=session.id,
                    action=chat_request.project_action,
                    data=chat_request.project_adjustments,
                ):
                    yield event.to_sse()
                yield "data: [DONE]\n\n"
                return
            except Exception as e:
                logger.error(f"Project action failed: {e}", exc_info=True)
                yield f'data: {{"error": "Project action failed: {str(e)}"}}\n\n'
                yield "data: [DONE]\n\n"
                return

        # Check for existing inline project that might need action
        from app.autonomous.inline_project import get_inline_project, InlineProjectStatus
        existing_project = get_inline_project(session.id)
        if existing_project and existing_project.is_active:
            from app.autonomous.inline_orchestrator import InlineOrchestrator

            # Check if this is a plan approval/rejection
            message_lower = actual_message.lower().strip()
            if existing_project.status == InlineProjectStatus.AWAITING_APPROVAL:
                if message_lower in ("start", "approve", "yes", "go", "proceed", "ok", "okay", "lgtm"):
                    # Approve and start execution
                    orchestrator = InlineOrchestrator(session.id, existing_project.workspace_path)
                    orchestrator.project = existing_project
                    async for event in orchestrator.approve_plan():
                        yield event.to_sse()
                    yield "data: [DONE]\n\n"
                    return
                elif message_lower in ("cancel", "no", "abort", "stop", "nevermind"):
                    # Cancel the project
                    orchestrator = InlineOrchestrator(session.id, existing_project.workspace_path)
                    orchestrator.project = existing_project
                    async for event in orchestrator.cancel_project():
                        yield event.to_sse()
                    yield "data: [DONE]\n\n"
                    return
                else:
                    # Treat as adjustment request
                    orchestrator = InlineOrchestrator(session.id, existing_project.workspace_path)
                    orchestrator.project = existing_project
                    async for event in orchestrator.adjust_plan({"message": actual_message}):
                        yield event.to_sse()
                    yield "data: [DONE]\n\n"
                    return
            else:
                # Project is executing - handle as interrupt
                orchestrator = InlineOrchestrator(session.id, existing_project.workspace_path)
                orchestrator.project = existing_project
                async for event in orchestrator._handle_interrupt(actual_message):
                    yield event.to_sse()
                yield "data: [DONE]\n\n"
                return

        # Detect if this message should trigger a project
        from app.autonomous.detection import project_detector
        detection_result = project_detector.detect(actual_message)

        if detection_result.should_project and agent_id == "mo":
            from app.autonomous.inline_orchestrator import InlineOrchestrator
            from app.autonomous.models import ProjectConfig

            # Get workspace from context or use default
            workspace = chat_request.context.get("workspace", "") if chat_request.context else ""

            orchestrator = InlineOrchestrator(session.id, workspace)

            try:
                async for event in orchestrator.detect_and_plan(
                    actual_message,
                    config=ProjectConfig(),
                ):
                    yield event.to_sse()
                yield "data: [DONE]\n\n"
                return
            except Exception as e:
                logger.error(f"Project detection/planning failed: {e}", exc_info=True)
                # Fall through to normal chat processing
                yield f'data: {{"content": "Note: Project mode unavailable, handling as regular request.\\n\\n"}}\n\n'

        # Auto-route: detect if this request should go directly to a specialized agent
        auto_route_agent, auto_route_task = detect_auto_route(actual_message)
        if auto_route_agent and agent_id == "mo":
            logger.info(f"Auto-routing to {auto_route_agent}: {auto_route_task[:50]}...")
            yield 'data: {"thinking": true}\n\n'
            yield f'data: {{"content": "Routing to {auto_route_agent} agent...\\n\\n"}}\n\n'
            yield 'data: {"thinking": false}\n\n'
            yield 'data: {"orchestrating": true}\n\n'

            try:
                task = await subagent_runner.run_task(
                    task_description=auto_route_task,
                    agent_id=auto_route_agent,
                    context=chat_request.context,
                    callback_session=session.id,
                )
                escaped_task = auto_route_task[:100].replace("\n", " ").replace('"', '\\"')
                yield f'data: {{"subagent": "{auto_route_agent}", "task_id": "{task.id}", "task": "{escaped_task}", "status": "running"}}\n\n'

                # Wait for completion
                while True:
                    await asyncio.sleep(1)
                    current = subagent_manager.get(task.id)
                    if not current:
                        break
                    if current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                        if current.status == TaskStatus.COMPLETED:
                            result_text = current.result.get("response", "") if current.result else ""
                            result_text = clean_cli_output(result_text)
                            result_text = convert_numbered_lines_to_codeblock(result_text)
                            yield f'data: {{"subagent": "{auto_route_agent}", "task_id": "{task.id}", "status": "completed"}}\n\n'
                            result_event = json.dumps({"subagent_result": auto_route_agent, "content": result_text})
                            yield f'data: {result_event}\n\n'
                            # Save to DB
                            async with db.begin():
                                subagent_msg = DBMessage(
                                    id=str(uuid.uuid4()),
                                    session_id=session.id,
                                    role="assistant",
                                    content=f"**[{auto_route_agent.upper()}]**\n\n{result_text}",
                                )
                                db.add(subagent_msg)
                        else:
                            error = current.error or "Unknown error"
                            yield f'data: {{"subagent": "{auto_route_agent}", "task_id": "{task.id}", "status": "failed", "error": "{error}"}}\n\n'
                        break
            except Exception as e:
                logger.error(f"Auto-route spawn failed: {e}")
                escaped_err = str(e).replace('"', '\\"').replace('\n', ' ')
                yield f'data: {{"error": "Failed to spawn agent: {escaped_err}"}}\n\n'

            yield 'data: {"orchestrating": false}\n\n'
            yield "data: [DONE]\n\n"
            return

        # If command returned a direct response, yield it and return
        if command_response:
            yield 'data: {"thinking": false}\n\n'
            escaped = command_response.replace("\n", "\\n").replace('"', '\\"')
            yield f'data: {{"content": "{escaped}"}}\n\n'

            # Save response
            try:
                async with db.begin():
                    db_assistant_msg = DBMessage(
                        id=str(uuid.uuid4()),
                        session_id=session.id,
                        role="assistant",
                        content=command_response,
                    )
                    db.add(db_assistant_msg)
                    session.updated_at = datetime.now()
            except SQLAlchemyError as e:
                logger.error(f"Failed to save command response: {e}", exc_info=True)

            yield "data: [DONE]\n\n"
            return

        # Signal thinking started
        yield 'data: {"thinking": true}\n\n'

        # Get memory context
        context = chat_request.context or {}

        # Pass user message for skill auto-detection
        context["user_message"] = actual_message

        try:
            from app.memory.manager import memory_manager
            from app.memory import MemoryError, MemoryStorageError
            memory_context = await memory_manager.get_context(
                query=actual_message,  # Use expanded message for memory search
                session_id=session.id,
                max_tokens=1000,
            )
            if memory_context:
                context["memory"] = memory_context
        except MemoryStorageError as e:
            # Storage error - log as error, may need investigation
            logger.error(f"Memory storage error: {e}", exc_info=True)
        except MemoryError as e:
            # General memory error - log as warning
            logger.warning(f"Memory system unavailable: {e}")
        except ImportError:
            # Memory module not available - this is fine
            logger.debug("Memory module not available")
        except Exception as e:
            # Unexpected error - log with full traceback for debugging
            logger.error(f"Unexpected memory error: {e}", exc_info=True)

        # Inject project context if loaded
        if project_context:
            context["project"] = project_context

        first_chunk = True
        in_model_thinking = False
        try:
            async for chunk in agent.chat(messages, context):
                # Handle thinking block markers
                if chunk == "__THINKING_START__":
                    in_model_thinking = True
                    yield 'data: {"model_thinking": true}\n\n'
                    continue
                elif chunk == "__THINKING_END__":
                    in_model_thinking = False
                    yield 'data: {"model_thinking": false}\n\n'
                    continue

                # Handle canvas tool events (from tool result data)
                if "__CANVAS_CREATE__" in chunk:
                    import re
                    canvas_match = re.search(r'__CANVAS_CREATE__(.+?)__CANVAS_END__', chunk)
                    if canvas_match:
                        artifact_json = canvas_match.group(1)
                        yield f'data: {{"canvas_create": {artifact_json}}}\n\n'
                        logger.info(f"Canvas tool created artifact")
                        # Remove the marker from chunk so it doesn't appear in content
                        chunk = re.sub(r'__CANVAS_CREATE__.+?__CANVAS_END__', '', chunk)
                        if not chunk.strip():
                            continue

                # Signal initial thinking done on first real content
                if first_chunk and chunk.strip():
                    yield 'data: {"thinking": false}\n\n'
                    first_chunk = False

                full_response += chunk
                escaped = chunk.replace("\n", "\\n").replace('"', '\\"')
                yield f'data: {{"content": "{escaped}"}}\n\n'
        except Exception as e:
            logger.error(f"Agent chat error: {e}", exc_info=True)
            escaped_err = str(e).replace('"', '\\"').replace('\n', ' ')
            yield f'data: {{"error": "{escaped_err}"}}\n\n'

        # Auto-execute skill workflows if applicable
        try:
            user_msg = request.message if hasattr(request, 'message') else (messages[-1].content if messages else "")
            async for workflow_chunk in agent.maybe_execute_skill_workflows(context, user_msg):
                full_response += workflow_chunk
                escaped = workflow_chunk.replace("\n", "\\n").replace('"', '\\"')
                yield f'data: {{"content": "{escaped}"}}\n\n'
        except Exception as e:
            logger.warning(f"Skill workflow error: {e}")

        # If no content was streamed, still signal thinking done
        if first_chunk:
            logger.warning(f"No content received from agent {agent_id}")
            yield 'data: {"thinking": false}\n\n'
        if in_model_thinking:
            yield 'data: {"model_thinking": false}\n\n'

        # Save assistant message (convert numbered lines to code blocks for cleaner display)
        processed_response = convert_numbered_lines_to_codeblock(full_response)
        message_id = str(uuid.uuid4())
        try:
            async with db.begin():
                db_assistant_msg = DBMessage(
                    id=message_id,
                    session_id=session.id,
                    role="assistant",
                    content=processed_response,
                )
                db.add(db_assistant_msg)
                # Update session timestamp
                session.updated_at = datetime.now()
        except SQLAlchemyError as e:
            logger.error(f"Failed to save assistant message: {e}", exc_info=True)
            # Don't fail the stream - message was already sent to client

        # Process canvas markers and emit SSE events
        try:
            canvas_artifacts = await process_canvas_markers(
                full_response, session.id, message_id
            )
            for artifact in canvas_artifacts:
                yield f'data: {{"canvas_create": {json.dumps(artifact)}}}\n\n'
                logger.info(f"Created canvas artifact: {artifact['type']} - {artifact['title']}")
        except Exception as e:
            logger.error(f"Canvas marker processing error: {e}", exc_info=True)

        # Process mermaid code blocks and create canvas artifacts (for kiro-cli output)
        try:
            mermaid_artifacts = await process_mermaid_blocks(
                full_response, session.id, message_id
            )
            for artifact in mermaid_artifacts:
                yield f'data: {{"canvas_create": {json.dumps(artifact)}}}\n\n'
                logger.info(f"Created mermaid canvas artifact: {artifact['title']}")
        except Exception as e:
            logger.error(f"Mermaid processing error: {e}", exc_info=True)

        # Generate better title for new sessions (first message)
        if len(db_messages) == 0 and full_response:
            try:
                new_title = await generate_title(chat_request.message, full_response)
                async with db.begin():
                    session.title = new_title
                logger.info(f"Generated session title: {new_title}")
            except SQLAlchemyError as e:
                logger.error(f"Failed to update title: {e}", exc_info=True)
            except Exception as e:
                logger.warning(f"Failed to generate title: {e}")
        
        # Store important exchanges in memory
        try:
            from app.memory.manager import memory_manager
            from app.memory import MemoryStorageError
            await memory_manager.extract_and_store(
                conversation=[
                    {"role": "user", "content": chat_request.message},
                    {"role": "assistant", "content": processed_response},
                ],
                session_id=session.id,
                agent_id=agent_id,
            )
        except MemoryStorageError as e:
            logger.error(f"Memory storage error: {e}", exc_info=True)
        except ImportError:
            pass  # Memory module not available
        except Exception as e:
            logger.error(f"Unexpected memory storage error: {e}", exc_info=True)

        # Check for [SPAWN:agent] markers and auto-orchestrate
        spawn_matches = SPAWN_PATTERN.findall(full_response)
        logger.info(f"Spawn matches found: {len(spawn_matches)}")
        
        if spawn_matches:
            yield 'data: {"orchestrating": true}\n\n'
            
            # Phase 1: Spawn all tasks in parallel
            running_tasks: list[tuple[str, Any]] = []  # (agent_id, task)
            
            for agent_id_spawn, task_desc in spawn_matches:
                logger.info(f"Spawning: {agent_id_spawn}")
                task_desc = task_desc.strip()
                if not task_desc:
                    continue
                
                # Validate agent exists
                valid_agents = ("architect", "reviewer", "coder", "tester", "docs", "devops", "mo")
                if agent_id_spawn not in valid_agents:
                    logger.warning(f"Unknown agent in SPAWN: {agent_id_spawn}")
                    continue
                
                # Notify client about spawned task
                escaped_task = task_desc[:100].replace("\n", " ").replace('"', '\\"')
                
                try:
                    # Spawn the subagent task (returns immediately, runs in background)
                    task = await subagent_runner.run_task(
                        task_description=task_desc,
                        agent_id=agent_id_spawn,
                        context=chat_request.context,
                        callback_session=session.id,
                    )
                    running_tasks.append((agent_id_spawn, task))
                    yield f'data: {{"subagent": "{agent_id_spawn}", "task_id": "{task.id}", "task": "{escaped_task}", "status": "running"}}\n\n'
                    logger.info(f"Spawned {agent_id_spawn} with task_id {task.id}")
                except Exception as e:
                    logger.error(f"Failed to spawn {agent_id_spawn}: {e}")
                    escaped_err = str(e).replace('"', '\\"').replace('\n', ' ')
                    yield f'data: {{"subagent": "{agent_id_spawn}", "status": "error", "error": "{escaped_err}"}}\n\n'
            
            # Phase 2: Poll all tasks in parallel until all complete
            last_progress: dict[str, float] = {}
            completed_tasks: set[str] = set()
            
            while len(completed_tasks) < len(running_tasks):
                await asyncio.sleep(1)
                
                for agent_id_spawn, task in running_tasks:
                    if task.id in completed_tasks:
                        continue
                    
                    current = subagent_manager.get(task.id)
                    if not current:
                        continue
                    
                    # Send progress updates with goal information
                    if current.progress != last_progress.get(task.id, 0):
                        last_progress[task.id] = current.progress

                        # Build progress event with goal data
                        progress_data = {
                            "subagent": agent_id_spawn,
                            "task_id": task.id,
                            "progress": round(current.progress, 2),
                        }

                        # Include goal tracking if available
                        if current.goals:
                            goals_completed = sum(1 for g in current.goals if g.status.value == "completed")
                            progress_data["goals"] = {
                                "total": len(current.goals),
                                "completed": goals_completed,
                                "current_id": current.current_goal_id,
                                "items": [
                                    {
                                        "id": g.id,
                                        "description": g.description[:100],
                                        "status": g.status.value,
                                    }
                                    for g in current.goals
                                ],
                            }

                        # Include checkpoints if available
                        if current.checkpoints:
                            progress_data["checkpoints"] = [
                                {"name": c.name, "description": c.description[:100]}
                                for c in current.checkpoints[-3:]  # Last 3 checkpoints
                            ]

                        yield f"data: {json.dumps(progress_data)}\n\n"
                    
                    # Check if completed
                    if current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                        completed_tasks.add(task.id)
                        logger.info(f"Subagent {agent_id_spawn} finished with status: {current.status}")
                        
                        if current.status == TaskStatus.COMPLETED:
                            result_text = current.result.get("response", "") if current.result else ""
                            # Clean CLI artifacts and convert numbered lines to code blocks
                            result_text = clean_cli_output(result_text)
                            result_text = convert_numbered_lines_to_codeblock(result_text)
                            logger.info(f"Subagent {agent_id_spawn} response length: {len(result_text)}")
                            
                            yield f'data: {{"subagent": "{agent_id_spawn}", "task_id": "{task.id}", "status": "completed"}}\n\n'
                            
                            # Stream result
                            result_event = json.dumps({
                                "subagent_result": agent_id_spawn,
                                "content": result_text
                            })
                            yield f'data: {result_event}\n\n'
                            
                            # Save to DB
                            async with db.begin():
                                subagent_msg = DBMessage(
                                    id=str(uuid.uuid4()),
                                    session_id=session.id,
                                    role="assistant",
                                    content=f"**[{agent_id_spawn.upper()}]**\n\n{result_text}",
                                )
                                db.add(subagent_msg)
                        else:
                            error = current.error or "Unknown error"
                            yield f'data: {{"subagent": "{agent_id_spawn}", "task_id": "{task.id}", "status": "failed", "error": "{error}"}}\n\n'
            
            yield 'data: {"orchestrating": false}\n\n'

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-ID": session.id,
            "X-Agent-ID": agent_id,
        },
    )


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[SessionResponse]:
    """List chat sessions."""
    result = await db.execute(
        select(DBSession).order_by(DBSession.updated_at.desc()).limit(limit)
    )
    sessions = result.scalars().all()
    return [
        SessionResponse(
            id=s.id,
            agent_id=s.agent_id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get session with messages."""
    result = await db.execute(select(DBSession).where(DBSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(DBMessage)
        .where(DBMessage.session_id == session_id)
        .order_by(DBMessage.created_at)
    )
    messages = result.scalars().all()

    return {
        "session": SessionResponse(
            id=session.id,
            agent_id=session.agent_id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
        ),
        "messages": [
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ],
    }


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a session and its messages."""
    result = await db.execute(select(DBSession).where(DBSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(DBMessage).where(DBMessage.session_id == session_id)
    )
    for msg in result.scalars().all():
        await db.delete(msg)

    await db.delete(session)
    await db.commit()

    return {"status": "deleted"}

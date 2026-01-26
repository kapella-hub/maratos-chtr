"""Chat API endpoints."""

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

        # Yield session ID and agent info first
        yield f"data: {{\"session_id\": \"{session.id}\", \"agent\": \"{agent_id}\"}}\n\n"

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

        # If no content was streamed, still signal thinking done
        if first_chunk:
            logger.warning(f"No content received from agent {agent_id}")
            yield 'data: {"thinking": false}\n\n'
        if in_model_thinking:
            yield 'data: {"model_thinking": false}\n\n'

        # Save assistant message (convert numbered lines to code blocks for cleaner display)
        processed_response = convert_numbered_lines_to_codeblock(full_response)
        try:
            async with db.begin():
                db_assistant_msg = DBMessage(
                    id=str(uuid.uuid4()),
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
                    
                    # Send progress updates
                    if current.progress != last_progress.get(task.id, 0):
                        last_progress[task.id] = current.progress
                        yield f'data: {{"subagent": "{agent_id_spawn}", "task_id": "{task.id}", "progress": {current.progress:.2f}}}\n\n'
                    
                    # Check if completed
                    if current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                        completed_tasks.add(task.id)
                        logger.info(f"Subagent {agent_id_spawn} finished with status: {current.status}")
                        
                        if current.status == TaskStatus.COMPLETED:
                            result_text = current.result.get("response", "") if current.result else ""
                            # Convert numbered line format to proper code blocks
                            result_text = convert_numbered_lines_to_codeblock(result_text)
                            logger.info(f"Subagent {agent_id_spawn} response length: {len(result_text)}")
                            
                            yield f'data: {{"subagent": "{agent_id_spawn}", "task_id": "{task.id}", "status": "completed"}}\n\n'
                            
                            # Stream result
                            import json
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

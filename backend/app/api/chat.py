"""Chat API endpoints."""

import re
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import agent_registry
from app.agents.base import Message
from app.database import Message as DBMessage
from app.database import Session as DBSession
from app.database import get_db
from app.subagents.runner import subagent_runner
from app.subagents.manager import subagent_manager, TaskStatus

logger = logging.getLogger(__name__)

# Pattern to match [SPAWN:agent_id] task description
SPAWN_PATTERN = re.compile(r'\[SPAWN:(\w+)\]\s*(.+?)(?=\[SPAWN:|\Z)', re.DOTALL)

router = APIRouter(prefix="/chat")


class ChatRequest(BaseModel):
    """Chat request body."""

    message: str
    session_id: str | None = None
    agent_id: str | None = None  # Optional: specify agent (mo, architect, reviewer)
    context: dict[str, Any] | None = None


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
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Send a message and stream the response."""
    # Get agent (use specified or registry default)
    if request.agent_id:
        agent = agent_registry.get(request.agent_id)
        agent_id = request.agent_id
    else:
        agent = agent_registry.get_default()
        agent_id = agent.id if agent else "mo"
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    # Get or create session
    if request.session_id:
        result = await db.execute(
            select(DBSession).where(DBSession.id == request.session_id)
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
            title=request.message[:100] if request.message else None,
        )
        db.add(session)
        await db.commit()

    # Load conversation history
    result = await db.execute(
        select(DBMessage)
        .where(DBMessage.session_id == session.id)
        .order_by(DBMessage.created_at)
    )
    db_messages = result.scalars().all()

    # Convert to Message objects
    messages = [
        Message(role=m.role, content=m.content, tool_calls=m.tool_calls)
        for m in db_messages
    ]

    # Add user message
    user_message = Message(role="user", content=request.message)
    messages.append(user_message)

    # Save user message
    db_user_msg = DBMessage(
        id=str(uuid.uuid4()),
        session_id=session.id,
        role="user",
        content=request.message,
    )
    db.add(db_user_msg)
    await db.commit()

    async def generate():
        """Generate streaming response."""
        full_response = ""

        # Yield session ID and agent info first
        yield f"data: {{\"session_id\": \"{session.id}\", \"agent\": \"{agent_id}\"}}\n\n"

        # Signal thinking started
        yield 'data: {"thinking": true}\n\n'

        first_chunk = True
        async for chunk in agent.chat(messages, request.context):
            # Signal thinking done on first content
            if first_chunk:
                yield 'data: {"thinking": false}\n\n'
                first_chunk = False
            
            full_response += chunk
            escaped = chunk.replace("\n", "\\n").replace('"', '\\"')
            yield f'data: {{"content": "{escaped}"}}\n\n'

        # If no content was streamed, still signal thinking done
        if first_chunk:
            yield 'data: {"thinking": false}\n\n'

        # Save assistant message
        async with db.begin():
            db_assistant_msg = DBMessage(
                id=str(uuid.uuid4()),
                session_id=session.id,
                role="assistant",
                content=full_response,
            )
            db.add(db_assistant_msg)

        # Check for [SPAWN:agent] markers and auto-orchestrate
        spawn_matches = SPAWN_PATTERN.findall(full_response)
        logger.info(f"Spawn matches found: {len(spawn_matches)}")
        
        if spawn_matches:
            yield 'data: {"orchestrating": true}\n\n'
            
            for agent_id_spawn, task_desc in spawn_matches:
                logger.info(f"Processing spawn: {agent_id_spawn}")
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
                yield f'data: {{"subagent": "{agent_id_spawn}", "task": "{escaped_task}", "status": "spawning"}}\n\n'
                
                try:
                    # Spawn the subagent task
                    task = await subagent_runner.run_task(
                        task_description=task_desc,
                        agent_id=agent_id_spawn,
                        context=request.context,
                        callback_session=session.id,
                    )
                    
                    yield f'data: {{"subagent": "{agent_id_spawn}", "task_id": "{task.id}", "status": "running"}}\n\n'
                    
                    # Wait for completion (with timeout - 5 min for complex tasks)
                    timeout = 300
                    elapsed = 0
                    last_progress = 0.0
                    while elapsed < timeout:
                        current = subagent_manager.get(task.id)
                        if current and current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                            logger.info(f"Subagent {agent_id_spawn} finished with status: {current.status}")
                            break
                        await asyncio.sleep(2)
                        elapsed += 2
                        
                        # Send progress updates (only when changed)
                        if current and current.progress != last_progress:
                            last_progress = current.progress
                            logger.info(f"Subagent {agent_id_spawn} progress: {current.progress:.0%}")
                            yield f'data: {{"subagent": "{agent_id_spawn}", "task_id": "{task.id}", "progress": {current.progress:.2f}}}\n\n'
                    
                    if elapsed >= timeout:
                        logger.warning(f"Subagent {agent_id_spawn} timed out after {timeout}s")
                    
                    # Get result
                    final_task = subagent_manager.get(task.id)
                    logger.info(f"Final task status: {final_task.status if final_task else 'None'}")
                    if final_task:
                        logger.info(f"Final task result: {final_task.result is not None}, error: {final_task.error}")
                    
                    if final_task and final_task.status == TaskStatus.COMPLETED:
                        result_text = final_task.result.get("response", "") if final_task.result else ""
                        logger.info(f"Subagent response length: {len(result_text)}")
                        
                        # Stream the subagent result
                        yield f'data: {{"subagent": "{agent_id_spawn}", "task_id": "{task.id}", "status": "completed"}}\n\n'
                        
                        # Stream result content (use proper JSON to escape all special chars)
                        import json
                        result_event = json.dumps({
                            "subagent_result": agent_id_spawn,
                            "content": result_text
                        })
                        logger.info(f"Sending subagent_result: agent={agent_id_spawn}, content_len={len(result_text)}")
                        yield f'data: {result_event}\n\n'
                        
                        logger.info(f"Sent subagent_result event successfully")
                        
                        # Save subagent result as a message
                        async with db.begin():
                            subagent_msg = DBMessage(
                                id=str(uuid.uuid4()),
                                session_id=session.id,
                                role="assistant",
                                content=f"**[{agent_id_spawn.upper()}]**\n\n{result_text}",
                            )
                            db.add(subagent_msg)
                    else:
                        error = final_task.error if final_task else "timeout"
                        yield f'data: {{"subagent": "{agent_id_spawn}", "task_id": "{task.id}", "status": "failed", "error": "{error}"}}\n\n'
                        
                except Exception as e:
                    import traceback
                    logger.error(f"Failed to spawn subagent {agent_id_spawn}: {e}\n{traceback.format_exc()}")
                    escaped_err = str(e).replace('"', '\\"').replace('\n', ' ')
                    yield f'data: {{"subagent": "{agent_id_spawn}", "status": "error", "error": "{escaped_err}"}}\n\n'
            
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
    limit: int = 50,
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

"""Session tools for cross-session communication and coordination."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, or_

from app.database import Session, Message, async_session_factory
from app.tools.base import Tool, ToolParameter, ToolResult, registry


class SessionsTool(Tool):
    """Tool for cross-session communication and coordination.

    Allows agents to:
    - List recent sessions
    - Read message history from other sessions
    - Search across all sessions
    - Get summarized context from a session
    """

    def __init__(self) -> None:
        super().__init__(
            id="sessions",
            name="Sessions",
            description="Access and search across chat sessions for context and coordination",
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action to perform",
                    enum=["list", "history", "search", "context"],
                ),
                ToolParameter(
                    name="session_id",
                    type="string",
                    description="Session ID (required for history/context actions)",
                    required=False,
                ),
                ToolParameter(
                    name="query",
                    type="string",
                    description="Search query (required for search action)",
                    required=False,
                ),
                ToolParameter(
                    name="limit",
                    type="number",
                    description="Max results to return (default: 10)",
                    required=False,
                    default=10,
                ),
                ToolParameter(
                    name="agent_filter",
                    type="string",
                    description="Filter by agent ID (optional for list action)",
                    required=False,
                ),
            ],
        )
        # Track current session to exclude from results
        self._current_session_id: str | None = None

    def set_current_session(self, session_id: str) -> None:
        """Set current session to exclude from cross-session queries."""
        self._current_session_id = session_id

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute session tool action."""
        action = kwargs.get("action")

        if action == "list":
            return await self._list_sessions(
                limit=int(kwargs.get("limit", 10)),
                agent_filter=kwargs.get("agent_filter"),
            )
        elif action == "history":
            session_id = kwargs.get("session_id")
            if not session_id:
                return ToolResult(
                    success=False,
                    output="",
                    error="session_id is required for history action",
                )
            return await self._get_history(
                session_id=session_id,
                limit=int(kwargs.get("limit", 50)),
            )
        elif action == "search":
            query = kwargs.get("query")
            if not query:
                return ToolResult(
                    success=False,
                    output="",
                    error="query is required for search action",
                )
            return await self._search_sessions(
                query=query,
                limit=int(kwargs.get("limit", 10)),
            )
        elif action == "context":
            session_id = kwargs.get("session_id")
            if not session_id:
                return ToolResult(
                    success=False,
                    output="",
                    error="session_id is required for context action",
                )
            return await self._get_context(session_id=session_id)
        else:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown action: {action}. Use: list, history, search, context",
            )

    async def _list_sessions(
        self, limit: int = 10, agent_filter: str | None = None
    ) -> ToolResult:
        """List recent sessions with previews."""
        async with async_session_factory() as db:
            # Build query
            query = select(Session).order_by(Session.updated_at.desc())

            if agent_filter:
                query = query.where(Session.agent_id == agent_filter)

            # Exclude current session
            if self._current_session_id:
                query = query.where(Session.id != self._current_session_id)

            query = query.limit(limit)

            result = await db.execute(query)
            sessions = result.scalars().all()

            if not sessions:
                return ToolResult(
                    success=True,
                    output="No other sessions found.",
                    data={"sessions": []},
                )

            # Get message counts and previews for each session
            session_data = []
            for session in sessions:
                # Get message count
                count_query = select(func.count(Message.id)).where(
                    Message.session_id == session.id
                )
                count_result = await db.execute(count_query)
                message_count = count_result.scalar() or 0

                # Get first user message as preview
                preview_query = (
                    select(Message.content)
                    .where(Message.session_id == session.id)
                    .where(Message.role == "user")
                    .order_by(Message.created_at.asc())
                    .limit(1)
                )
                preview_result = await db.execute(preview_query)
                preview = preview_result.scalar()
                if preview:
                    preview = preview[:100] + "..." if len(preview) > 100 else preview

                session_data.append({
                    "id": session.id,
                    "title": session.title or "(untitled)",
                    "agent_id": session.agent_id,
                    "message_count": message_count,
                    "preview": preview or "(no messages)",
                    "updated_at": session.updated_at.isoformat(),
                })

            # Format output
            output_lines = ["## Recent Sessions\n"]
            for s in session_data:
                output_lines.append(
                    f"- **{s['title']}** (id: `{s['id'][:8]}...`)\n"
                    f"  Agent: {s['agent_id']} | Messages: {s['message_count']} | "
                    f"Updated: {s['updated_at'][:10]}\n"
                    f"  Preview: {s['preview']}\n"
                )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data={"sessions": session_data},
            )

    async def _get_history(self, session_id: str, limit: int = 50) -> ToolResult:
        """Get message history from a specific session."""
        async with async_session_factory() as db:
            # Get session
            session_query = select(Session).where(Session.id == session_id)
            session_result = await db.execute(session_query)
            session = session_result.scalar_one_or_none()

            if not session:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Session not found: {session_id}",
                )

            # Get messages
            messages_query = (
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.asc())
                .limit(limit)
            )
            messages_result = await db.execute(messages_query)
            messages = messages_result.scalars().all()

            if not messages:
                return ToolResult(
                    success=True,
                    output=f"Session '{session.title}' has no messages.",
                    data={"session": {"id": session.id, "title": session.title}, "messages": []},
                )

            # Format output
            output_lines = [
                f"## Session: {session.title or '(untitled)'}",
                f"Agent: {session.agent_id} | Created: {session.created_at.isoformat()[:10]}\n",
                "---\n",
            ]

            message_data = []
            for msg in messages:
                role_icon = {"user": "👤", "assistant": "🤖", "system": "⚙️", "tool": "🔧"}.get(
                    msg.role, "💬"
                )
                content_preview = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
                output_lines.append(f"{role_icon} **{msg.role.upper()}**: {content_preview}\n")

                message_data.append({
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat(),
                })

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data={
                    "session": {
                        "id": session.id,
                        "title": session.title,
                        "agent_id": session.agent_id,
                    },
                    "messages": message_data,
                },
            )

    async def _search_sessions(self, query: str, limit: int = 10) -> ToolResult:
        """Search for messages across all sessions."""
        async with async_session_factory() as db:
            # Search in message content (simple LIKE query)
            # For SQLite, use LIKE; for production consider full-text search
            search_pattern = f"%{query}%"

            messages_query = (
                select(Message, Session)
                .join(Session, Message.session_id == Session.id)
                .where(Message.content.ilike(search_pattern))
                .order_by(Message.created_at.desc())
                .limit(limit)
            )

            # Exclude current session
            if self._current_session_id:
                messages_query = messages_query.where(
                    Session.id != self._current_session_id
                )

            result = await db.execute(messages_query)
            rows = result.all()

            if not rows:
                return ToolResult(
                    success=True,
                    output=f"No matches found for: {query}",
                    data={"matches": []},
                )

            # Group by session
            sessions_map: dict[str, dict] = {}
            for msg, session in rows:
                if session.id not in sessions_map:
                    sessions_map[session.id] = {
                        "session_id": session.id,
                        "title": session.title or "(untitled)",
                        "agent_id": session.agent_id,
                        "matches": [],
                    }
                sessions_map[session.id]["matches"].append({
                    "message_id": msg.id,
                    "role": msg.role,
                    "content": msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
                    "created_at": msg.created_at.isoformat(),
                })

            # Format output
            output_lines = [f"## Search Results for: {query}\n"]
            for session_data in sessions_map.values():
                output_lines.append(
                    f"### {session_data['title']} (`{session_data['session_id'][:8]}...`)\n"
                )
                for match in session_data["matches"]:
                    output_lines.append(
                        f"- [{match['role']}] {match['content']}\n"
                    )
                output_lines.append("")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data={"matches": list(sessions_map.values())},
            )

    async def _get_context(self, session_id: str) -> ToolResult:
        """Get summarized context from a session.

        Returns key information:
        - Session title and metadata
        - Main topics discussed
        - Key decisions made
        - Files mentioned/modified
        """
        async with async_session_factory() as db:
            # Get session
            session_query = select(Session).where(Session.id == session_id)
            session_result = await db.execute(session_query)
            session = session_result.scalar_one_or_none()

            if not session:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Session not found: {session_id}",
                )

            # Get all messages
            messages_query = (
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.asc())
            )
            messages_result = await db.execute(messages_query)
            messages = messages_result.scalars().all()

            if not messages:
                return ToolResult(
                    success=True,
                    output=f"Session '{session.title}' has no messages.",
                    data={"context": {}},
                )

            # Extract context information
            user_messages = [m for m in messages if m.role == "user"]
            assistant_messages = [m for m in messages if m.role == "assistant"]

            # Find mentioned file paths (simple heuristic)
            import re
            file_pattern = r'(?:/[\w.-]+)+(?:\.\w+)?'
            all_content = " ".join(m.content for m in messages)
            mentioned_files = list(set(re.findall(file_pattern, all_content)))[:10]

            # Get first and last user messages as topic indicators
            first_request = user_messages[0].content[:200] if user_messages else ""
            last_request = user_messages[-1].content[:200] if len(user_messages) > 1 else ""

            # Build context summary
            context = {
                "session_id": session.id,
                "title": session.title,
                "agent_id": session.agent_id,
                "message_count": len(messages),
                "user_message_count": len(user_messages),
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "initial_request": first_request,
                "latest_request": last_request if last_request != first_request else None,
                "mentioned_files": mentioned_files,
            }

            # Format output
            output = f"""## Session Context: {session.title or '(untitled)'}

**Agent:** {session.agent_id}
**Messages:** {len(messages)} total ({len(user_messages)} from user)
**Duration:** {session.created_at.isoformat()[:10]} to {session.updated_at.isoformat()[:10]}

### Initial Request
{first_request}...

"""
            if context["latest_request"]:
                output += f"""### Latest Request
{last_request}...

"""
            if mentioned_files:
                output += "### Files Mentioned\n"
                for f in mentioned_files[:5]:
                    output += f"- `{f}`\n"

            return ToolResult(
                success=True,
                output=output,
                data={"context": context},
            )


# Register the tool
sessions_tool = SessionsTool()
registry.register(sessions_tool)

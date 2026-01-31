
"""Collaboration tools for agent handoffs."""

from typing import Any, Dict, List
from app.tools.base import Tool, ToolParameter, ToolResult
from app.collaboration.handoff import HandoffManager

class CreateHandoffTool(Tool):
    """Tool to create a structured handoff to another agent."""

    def __init__(self):
        super().__init__(
            id="create_handoff",
            name="Create Handoff",
            description=(
                "Create a handoff context to pass control to another agent. "
                "Use this when you finish your part of the task (e.g., coding) and need another agent "
                "(e.g., tester) to take over."
            ),
            parameters=[
                ToolParameter(
                    name="to_agent",
                    type="string",
                    description="The ID of the target agent (e.g., 'tester', 'reviewer')",
                ),
                ToolParameter(
                    name="task_description",
                    type="string",
                    description="Description of what needs to be done next",
                ),
                ToolParameter(
                    name="files_modified",
                    type="array",
                    description="List of files modified",
                    required=False,
                    default=[],
                ),
                ToolParameter(
                    name="key_decisions",
                    type="array",
                    description="List of key decisions made",
                    required=False,
                    default=[],
                ),
            ],
        )
        self.manager = HandoffManager()

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the handoff creation."""
        try:
            to_agent = kwargs.get("to_agent")
            task_description = kwargs.get("task_description")
            files_modified = kwargs.get("files_modified", [])
            key_decisions = kwargs.get("key_decisions", [])
            
            # In a real system, we'd get the 'from_agent' from the context or session.
            # For now, we default 'mo' or get it from kwargs if injected.
            from_agent = kwargs.get("agent_id", "mo") 
            
            handoff = self.manager.create_handoff(
                from_agent=from_agent,
                to_agent=to_agent,
                task_description=task_description,
                files_modified=files_modified,
                key_decisions=key_decisions
            )
            
            # Serialize to JSON - in a real system this would trigger the dispatch event
            json_str = self.manager.serialize(handoff)
            
            return ToolResult(
                success=True,
                output=f"Handoff created for agent '{to_agent}'\nID: {handoff.id}",
                data={
                    "handoff_id": handoff.id,
                    "handoff_preview": json_str[:500]
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

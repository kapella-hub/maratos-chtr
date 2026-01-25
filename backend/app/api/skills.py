"""Skills API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.skills.base import skill_registry
from app.skills.executor import SkillExecutor

router = APIRouter(prefix="/skills")


class ExecuteSkillRequest(BaseModel):
    """Request to execute a skill."""
    context: dict[str, Any] | None = None
    workdir: str | None = None


@router.get("")
async def list_skills() -> list[dict[str, Any]]:
    """List all available skills."""
    return skill_registry.list_all()


@router.get("/search")
async def search_skills(q: str) -> list[dict[str, Any]]:
    """Search skills by query."""
    skills = skill_registry.search(q)
    return [s.to_dict() for s in skills]


@router.get("/{skill_id}")
async def get_skill(skill_id: str) -> dict[str, Any]:
    """Get skill details."""
    skill = skill_registry.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")
    
    return {
        **skill.to_dict(),
        "system_context": skill.system_context,
        "quality_checklist": skill.quality_checklist,
        "test_requirements": skill.test_requirements,
        "workflow": [
            {
                "name": step.name,
                "action": step.action,
                "description": step.description,
            }
            for step in skill.workflow
        ],
    }


@router.post("/{skill_id}/execute")
async def execute_skill(skill_id: str, request: ExecuteSkillRequest) -> dict[str, Any]:
    """Execute a skill workflow."""
    skill = skill_registry.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")
    
    context = request.context or {}
    if request.workdir:
        context["workdir"] = request.workdir
    
    executor = SkillExecutor(workdir=request.workdir)
    result = await executor.execute(skill, context)
    
    return result

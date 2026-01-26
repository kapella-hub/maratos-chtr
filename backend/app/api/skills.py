"""Skills API endpoints."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.skills.base import skill_registry
from app.skills.executor import SkillExecutor
from app.skills.loader import (
    get_validation_results,
    validate_all_skills,
    validate_skill_yaml,
)

router = APIRouter(prefix="/skills")


class ExecuteSkillRequest(BaseModel):
    """Request to execute a skill."""
    context: dict[str, Any] | None = None
    workdir: str | None = None


class MatchSkillRequest(BaseModel):
    """Request to match skills to a prompt."""
    prompt: str


@router.get("")
async def list_skills() -> list[dict[str, Any]]:
    """List all available skills."""
    return skill_registry.list_all()


@router.get("/search")
async def search_skills(q: str) -> list[dict[str, Any]]:
    """Search skills by query."""
    skills = skill_registry.search(q)
    return [s.to_dict() for s in skills]


@router.post("/match")
async def match_skills(request: MatchSkillRequest) -> dict[str, Any]:
    """Match skills to a user prompt based on triggers.

    Returns skills that match the prompt, sorted by relevance.
    """
    prompt_lower = request.prompt.lower()
    matches = []

    for skill in skill_registry.search(""):  # Get all skills
        score = 0
        matched_triggers = []

        for trigger in skill.triggers:
            trigger_lower = trigger.lower()
            if trigger_lower in prompt_lower:
                score += len(trigger)  # Longer matches score higher
                matched_triggers.append(trigger)

        # Also check tags
        for tag in skill.tags:
            if tag.lower() in prompt_lower:
                score += 1

        if score > 0:
            matches.append({
                **skill.to_dict(),
                "match_score": score,
                "matched_triggers": matched_triggers,
            })

    # Sort by score descending
    matches.sort(key=lambda x: x["match_score"], reverse=True)

    return {
        "prompt": request.prompt,
        "matches": matches,
        "best_match": matches[0] if matches else None,
    }


@router.get("/validation")
async def get_skill_validation() -> dict[str, Any]:
    """Get validation results from skill loading.

    Returns validation status for all loaded skills.
    """
    results = get_validation_results()
    return {
        "total": len(results),
        "valid": sum(1 for r in results if r.valid),
        "invalid": sum(1 for r in results if not r.valid),
        "results": [r.to_dict() for r in results],
    }


@router.post("/validate")
async def validate_skills() -> dict[str, Any]:
    """Validate all skills in the skills directory.

    Validates without reloading skills.
    """
    skills_dir = Path(settings.skills_dir).expanduser()
    results = validate_all_skills(skills_dir)

    return {
        "skills_dir": str(skills_dir),
        "total": len(results),
        "valid": sum(1 for r in results if r.valid),
        "invalid": sum(1 for r in results if not r.valid),
        "results": [r.to_dict() for r in results],
    }


@router.get("/{skill_id}")
async def get_skill(skill_id: str) -> dict[str, Any]:
    """Get skill details including workflow and quality checklist."""
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

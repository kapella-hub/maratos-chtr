"""Rules API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.rules import (
    Rule,
    list_rules,
    get_rule,
    create_rule,
    update_rule,
    delete_rule,
    rules_exist,
    create_example_rules,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class RuleCreate(BaseModel):
    """Request body for creating a rule."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    content: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)


class RuleUpdate(BaseModel):
    """Request body for updating a rule."""
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    content: str | None = None
    tags: list[str] | None = None


class RuleResponse(BaseModel):
    """Rule response model."""
    id: str
    name: str
    description: str
    content: str
    tags: list[str]
    created_at: str
    updated_at: str


class RuleListItem(BaseModel):
    """Rule list item (without full content)."""
    id: str
    name: str
    description: str
    tags: list[str]
    created_at: str
    updated_at: str


def _rule_to_response(rule: Rule) -> RuleResponse:
    """Convert Rule to response model."""
    return RuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        content=rule.content,
        tags=rule.tags,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _rule_to_list_item(rule: Rule) -> RuleListItem:
    """Convert Rule to list item model."""
    return RuleListItem(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        tags=rule.tags,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("", response_model=list[RuleListItem])
async def list_all_rules() -> list[RuleListItem]:
    """List all rules.

    Returns rule metadata without full content.
    """
    rules = list_rules()
    return [_rule_to_list_item(r) for r in rules]


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule_by_id(rule_id: str) -> RuleResponse:
    """Get a single rule with full content."""
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return _rule_to_response(rule)


@router.post("", response_model=RuleResponse)
async def create_new_rule(data: RuleCreate) -> RuleResponse:
    """Create a new rule."""
    rule = create_rule(
        name=data.name,
        description=data.description,
        content=data.content,
        tags=data.tags,
    )
    return _rule_to_response(rule)


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_existing_rule(rule_id: str, data: RuleUpdate) -> RuleResponse:
    """Update an existing rule."""
    rule = update_rule(
        rule_id=rule_id,
        name=data.name,
        description=data.description,
        content=data.content,
        tags=data.tags,
    )
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return _rule_to_response(rule)


@router.delete("/{rule_id}")
async def delete_existing_rule(rule_id: str) -> dict[str, str]:
    """Delete a rule."""
    deleted = delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return {"status": "deleted", "id": rule_id}


@router.post("/examples", response_model=list[RuleResponse])
async def create_examples() -> list[RuleResponse]:
    """Create example rules.

    Only creates examples if no rules exist yet.
    """
    if rules_exist():
        raise HTTPException(
            status_code=400,
            detail="Rules already exist. Delete existing rules first to create examples."
        )

    rules = create_example_rules()
    return [_rule_to_response(r) for r in rules]

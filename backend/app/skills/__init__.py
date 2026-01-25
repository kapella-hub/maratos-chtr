"""Skills system for MaratOS - compatible with Kiro AI."""

from app.skills.base import Skill, SkillRegistry
from app.skills.loader import load_skills_from_dir

__all__ = ["Skill", "SkillRegistry", "load_skills_from_dir"]

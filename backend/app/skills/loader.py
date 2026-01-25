"""Skill loader for MaratOS."""

import logging
from pathlib import Path

from app.skills.base import Skill, skill_registry

logger = logging.getLogger(__name__)


def load_skills_from_dir(skills_dir: Path) -> int:
    """Load all skills from a directory.
    
    Returns the number of skills loaded.
    """
    if not skills_dir.exists():
        logger.info(f"Skills directory does not exist: {skills_dir}")
        return 0
    
    count = 0
    for path in skills_dir.glob("**/*.yaml"):
        try:
            skill = Skill.from_yaml(path)
            skill_registry.register(skill)
            logger.info(f"Loaded skill: {skill.id} from {path}")
            count += 1
        except Exception as e:
            logger.error(f"Failed to load skill from {path}: {e}")
    
    for path in skills_dir.glob("**/*.yml"):
        try:
            skill = Skill.from_yaml(path)
            skill_registry.register(skill)
            logger.info(f"Loaded skill: {skill.id} from {path}")
            count += 1
        except Exception as e:
            logger.error(f"Failed to load skill from {path}: {e}")
    
    return count

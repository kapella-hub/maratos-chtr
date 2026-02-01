import yaml
from pathlib import Path
from typing import Any

# Path to backend/data/prompts.yaml
# this file is in backend/app/prompts.py -> parent=app -> parent=backend -> data/prompts.yaml
PROMPTS_FILE = Path(__file__).parents[1] / "data" / "prompts.yaml"

_prompts_cache = {}

def load_prompts(force_reload: bool = False) -> dict[str, Any]:
    """Load prompts from YAML file."""
    global _prompts_cache
    if _prompts_cache and not force_reload:
        return _prompts_cache

    if not PROMPTS_FILE.exists():
        return {}

    try:
        with open(PROMPTS_FILE, "r") as f:
            _prompts_cache = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Error loading prompts: {e}")
        return {}

    return _prompts_cache

def get_prompt(key: str, default: str = "") -> str:
    """Get a prompt by dot-notation key (e.g. 'agent_prompts.coder')."""
    prompts = load_prompts()
    
    # Support dot notation
    keys = key.split(".")
    value = prompts
    
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default
            
    
    if value is None:
        return default
        
    # Automatic Shared Injection
    # If we are retrieving an agent prompt (string), inject shared variables if present
    if isinstance(value, str) and "shared_" in value and "render_hints" in prompts:
        try:
            injectables = prompts.get("render_hints", {}).get("injectables", {})
            # Only format if we have injectables and the string looks like it needs them
            if injectables:
                # We use safe_format (or strict, depending on preference). 
                # Here we do a partial format to resolve shared_* but leave tool_section for later.
                # However, python's .format() is all-or-nothing.
                # Strategy: We will replace {shared_X} manually to avoid breaking {tool_section}
                for share_key, share_val in injectables.items():
                    placeholder = f"{{{share_key}}}"
                    if placeholder in value:
                        value = value.replace(placeholder, str(share_val))
        except Exception as e:
            print(f"Warning: Failed to inject shared prompt variables: {e}")

    return str(value)

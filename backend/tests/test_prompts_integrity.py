
import pytest
from app.prompts import load_prompts, get_prompt

def test_prompts_file_exists_and_loads():
    """Verify prompts.yaml is loadable and valid JSON/YAML."""
    prompts = load_prompts(force_reload=True)
    assert prompts, "Failed to load prompts.yaml"
    assert "agent_prompts" in prompts, "prompts.yaml missing 'agent_prompts' key"

def test_coder_prompt_has_proactive_rules():
    """Harden: Ensure Coder instructions include Adaptive Execution and Boy Scout rules."""
    coder_prompt = get_prompt("agent_prompts.coder")
    
    # Check for Adaptive Execution
    assert "Adaptive Execution" in coder_prompt, "Coder prompt missing 'Adaptive Execution' section"
    assert "Plan Deviation" in coder_prompt, "Coder prompt missing 'Plan Deviation' permission"
    assert "Scope Expansion" in coder_prompt, "Coder prompt missing 'Scope Expansion' permission"
    
    # Check for Boy Scout Rule
    assert "Boy Scout Rule" in coder_prompt, "Coder prompt missing 'Boy Scout Rule'"
    assert "Self-Healing" in coder_prompt, "Coder prompt missing 'Self-Healing' instruction"

def test_reviewer_prompt_has_operational_task_support():
    """Harden: Ensure Reviewer knows how to handle deployment/ops tasks (logs vs files)."""
    reviewer_prompt = get_prompt("agent_prompts.reviewer")
    
    assert "Operational/Deployment Tasks" in reviewer_prompt, "Reviewer prompt missing 'Operational/Deployment Tasks' section"
    assert "Check the OUTPUT LOGS" in reviewer_prompt, "Reviewer prompt missing instruction to check logs"
    assert "no code was changed" in reviewer_prompt, "Reviewer prompt missing 'no code changed' override"

def test_architect_prompt_is_opinionated():
    """Harden: Ensure Architect is instructed to be an active CTO, not passive."""
    architect_prompt = get_prompt("agent_prompts.architect")
    
    assert "Proactive Planning" in architect_prompt, "Architect prompt missing 'Proactive Planning' section"
    assert "You are a CTO" in architect_prompt, "Architect prompt missing CTO persona"
    assert "Fill the gaps" in architect_prompt, "Architect missing instruction to fill requirements gaps"

def test_prompt_versions_aligned():
    """Ensure versions match expected."""
    prompts = load_prompts()
    assert prompts.get("meta", {}).get("version") == "0.4.0", "prompts.yaml version mismatch"

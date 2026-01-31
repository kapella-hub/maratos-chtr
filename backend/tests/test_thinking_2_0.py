
import pytest
from app.thinking.templates import get_templates, TemplateCategory, ThinkingStepType
from app.thinking.models import ThinkingLevel, TaskType
from app.thinking.adaptive import get_adaptive_manager

def test_load_templates():
    """Verify that templates are correctly loaded from YAML."""
    templates = get_templates()
    all_templates = templates.get_all()
    
    assert len(all_templates) >= 7 # We created 7 templates
    
    # Check specific templates
    code_review = templates.get("code_review")
    assert code_review is not None
    assert code_review.category == TemplateCategory.CODE
    assert len(code_review.focus_areas) > 0
    assert ThinkingStepType.ANALYSIS in code_review.required_steps
    
    security = templates.get("security_analysis")
    assert security is not None
    assert security.min_level == ThinkingLevel.HIGH
    assert "OWASP" in security.prompt_additions

def test_adaptive_logic_simple():
    """Verify adaptive logic for simple messages."""
    manager = get_adaptive_manager()
    
    # Simple greeting
    result = manager.determine_level("Hello world", ThinkingLevel.MEDIUM)
    assert result.complexity_score < 0.3
    assert result.adaptive_level == ThinkingLevel.MINIMAL or result.adaptive_level == ThinkingLevel.LOW

def test_adaptive_logic_complex_security():
    """Verify adaptive logic for complex security tasks."""
    manager = get_adaptive_manager()
    
    # Complex security request
    msg = "I need you to fix a critical SQL injection vulnerability in the auth module. Check for other exploits too."
    result = manager.determine_level(msg, ThinkingLevel.MEDIUM)
    
    # Should detect security task
    assert result.factors.detected_task_type == TaskType.SECURITY
    assert result.factors.security_indicators > 0
    
    # Should resolve to HIGH or MAX
    assert result.complexity_score > 0.6
    assert result.adaptive_level in (ThinkingLevel.HIGH, ThinkingLevel.MAX)

def test_adaptive_logic_debugging():
    """Verify adaptive logic for debugging."""
    manager = get_adaptive_manager()
    
    # Debugging request
    msg = "I'm getting a traceback error in `api.py` line 50. It crashes on startup. Can you debug this race condition?"
    result = manager.determine_level(msg, ThinkingLevel.MEDIUM)
    
    assert result.factors.detected_task_type == TaskType.DEBUGGING
    assert result.factors.error_indicators > 0
    assert result.complexity_score > 0.4 
    
def test_task_type_detection():
    """Verify specific task type detection heuristics."""
    manager = get_adaptive_manager()
    
    # Architecture
    assert manager.analyze_complexity("Design a scalable microservice architecture").detected_task_type == TaskType.ARCHITECTURE
    
    # Implementation
    assert manager.analyze_complexity("Implement a user login feature with JWT").detected_task_type == TaskType.IMPLEMENTATION
    
    # Refactoring
    assert manager.analyze_complexity("Refactor the `utils.py` module to be cleaner").detected_task_type == TaskType.REFACTORING

if __name__ == "__main__":
    # verification script
    try:
        test_load_templates()
        print("✅ Templates loaded successfully")
        test_adaptive_logic_simple()
        print("✅ Simple logic passed")
        test_adaptive_logic_complex_security()
        print("✅ Security logic passed")
        test_adaptive_logic_debugging()
        print("✅ Debugging logic passed")
        test_task_type_detection()
        print("✅ Task type detection passed")
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()

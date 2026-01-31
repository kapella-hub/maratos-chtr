
import pytest
from app.thinking.manager import ThinkingManager
from app.thinking.models import ThinkingStepType

def test_parse_legacy_format():
    """Test parsing [TYPE] content style."""
    manager = ThinkingManager()
    content = """
    [ANALYSIS]
    This is the analysis.
    [DECISION]
    This is the decision.
    """
    steps = manager.parse_legacy_content(content)
    assert len(steps) == 2
    assert steps[0].type == ThinkingStepType.ANALYSIS
    assert "This is the analysis" in steps[0].content
    assert steps[1].type == ThinkingStepType.DECISION
    assert "This is the decision" in steps[1].content

def test_parse_markdown_header_format():
    """Test parsing # Type style."""
    manager = ThinkingManager()
    content = """
    # Analysis
    Analyzing the request.
    ## Evaluation
    Evaluating options.
    """
    steps = manager.parse_legacy_content(content)
    assert len(steps) == 2
    assert steps[0].type == ThinkingStepType.ANALYSIS
    assert "Analyzing the request" in steps[0].content
    assert steps[1].type == ThinkingStepType.EVALUATION
    assert "Evaluating options" in steps[1].content

def test_parse_bold_colon_format():
    """Test parsing **Type**: style."""
    manager = ThinkingManager()
    content = """
    **Analysis**:
    Here is the analysis.
    
    **Risk**:
    There is a high risk.
    """
    steps = manager.parse_legacy_content(content)
    assert len(steps) == 2
    assert steps[0].type == ThinkingStepType.ANALYSIS
    assert "Here is the analysis" in steps[0].content
    assert steps[1].type == ThinkingStepType.RISK_ASSESSMENT
    assert "There is a high risk" in steps[1].content

def test_parse_mixed_format():
    """Test parsing mixed formats."""
    manager = ThinkingManager()
    content = """
    [ANALYSIS]
    Standard block.
    
    # Decision
    Markdown block.
    """
    steps = manager.parse_legacy_content(content)
    assert len(steps) == 2
    assert steps[0].type == ThinkingStepType.ANALYSIS
    assert steps[1].type == ThinkingStepType.DECISION

if __name__ == "__main__":
    try:
        test_parse_legacy_format()
        print("✅ Legacy format passed")
        test_parse_markdown_header_format()
        print("✅ Markdown header format passed")
        test_parse_bold_colon_format()
        print("✅ Bold colon format passed")
        test_parse_mixed_format()
        print("✅ Mixed format passed")
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()

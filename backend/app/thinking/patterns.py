"""Regex patterns for parsing thinking content."""

import re

# Patterns for parsing legacy XML-style thinking tags
THINKING_START_PATTERN = re.compile(r"<thinking>|<analysis>|\[THINKING\]", re.IGNORECASE)
THINKING_END_PATTERN = re.compile(r"</thinking>|</analysis>|\[/THINKING\]", re.IGNORECASE)

# Robust pattern for parsing step markers within thinking blocks
# Handles:
# - [ANALYSIS] or [Analysis]
# - ### Analysis
# - **Analysis** or **Analysis**:
# - Analysis:
# - # Analysis
STEP_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:\[|#+\s*|\*\*?|)(?P<type>ANALYSIS|EVALUATION|DECISION|VALIDATION|RISK|IMPLEMENTATION|CRITIQUE|TOOL_CALL|TOOL_RESULT)(?:\]|:|\*\*?|)\s*\n?"
    r"(?P<content>.*?)(?=(?:^|\n)\s*(?:\[|#+\s*|\*\*?|)(?:ANALYSIS|EVALUATION|DECISION|VALIDATION|RISK|IMPLEMENTATION|CRITIQUE|TOOL_CALL|TOOL_RESULT)(?:\]|:|\*\*?|)|\Z)",
    re.IGNORECASE | re.DOTALL
)

# Individual step type mapping (for normalization)
STEP_TYPE_MAP = {
    "ANALYSIS": "ANALYSIS",
    "EVALUATION": "EVALUATION",
    "DECISION": "DECISION",
    "VALIDATION": "VALIDATION",
    "RISK": "RISK_ASSESSMENT",
    "IMPLEMENTATION": "IMPLEMENTATION",
    "CRITIQUE": "CRITIQUE",
    "TOOL_CALL": "TOOL_CALL",
    "TOOL_RESULT": "TOOL_RESULT",
}

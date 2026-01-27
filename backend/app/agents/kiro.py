"""Kiro CLI agent - uses kiro-cli for Claude models via AWS."""

import asyncio
import re
import shutil
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.agents.base import Agent, AgentConfig
from app.tools.base import registry as tool_registry
import json

# Regex to strip ANSI escape codes
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# Patterns for verbose tool logs to filter out (line-based)
TOOL_LOG_PATTERNS = [
    r'^Reading (?:directory|file):.*',
    r'^Batch \w+ operation.*',
    r'^↱ Operation \d+:.*',
    r'^[✓✔☑✗✘❌]\s*(?:Successfully|Failed).*',  # Various checkmark/x characters
    r'^(?:Successfully|Failed)\s+(?:read|wrote|deleted|copied).*',  # Without checkmark
    r'^⋮\s*$',  # Just the ellipsis character alone
    r'^⋮.*',  # Ellipsis with anything after
    r'^\s*Summary:.*',
    r'^•?\s*Completed in.*',  # With or without bullet
    r'.*\(using tool:.*\).*',
    r'^\d+;\d+m.*entries.*',
    r'^\s*\[\d+ more items found\].*',
    r'^\[Overview\].*bytes.*tokens.*',
    r'^\d+ \w+ at /.*:\d+:\d+$',  # "1 Class RequestData at /path:30:1"
    r'^\(\d+ more items found\)$',
    r'^Searching.*\.\.\..*',  # "Searching in /path..."
    r'^Found \d+ (?:files?|matches?).*',  # "Found 5 files..."
    r'^Purpose:.*',  # "Purpose: ..."
    r'^Updating:.*',  # "Updating: path"
    r'^Creating:.*',  # "Creating: path"
    r'^Deleting:.*',  # "Deleting: path"
    r'^\d+ operations? processed.*',  # "2 operations processed, 2 successful"
    # Kiro CLI startup noise
    r'^Model:.*$',  # "Model: claude-sonnet-4 (/model to change)"
    r'^Did you know\?.*$',
    r'^You can use.*$',
    r'^\s*experience\s*$',
    r'^Time:.*$',
    r'^\s*▸\s*Time:.*$',  # " ▸ Time: 2s"
    r'^[•\-\s]*Completed in \d+\.?\d*s?.*$',  # " - Completed in 0.0s"
    r'^Now let me analyze.*$',
    r'^Let me start by reading.*$',
    r'^I\'ll (?:start|begin|conduct|analyze|review).*$',  # Transitional phrases
]

# Pattern for kiro banner (ASCII art and boxes)
KIRO_BANNER_PATTERNS = [
    r'^[╭╮╰╯│─]+',  # Box drawing characters
    r'^\s*[⢀⣴⣶⣦⡀⠀⣾⣿⠋⠁⠈⠙⡆⢀⢻⡆⢰⣇⡿⠀⣼⠇⢸⣤⣄⠉⡇⠹⣷⣆⣸⣠⣿⠃⢿⢹⣧⠻⣦⢴⠟⣤⣼⢀⣠⣴⣤⣄⡀⠈⠙⣷⡀⣶⡄⢸⠹⠁]+',  # Kiro banner characters
    r'^\s*$',  # Empty lines in the banner area
]

def is_tool_log_line(line: str) -> bool:
    """Check if a line is a tool execution log."""
    # Check tool log patterns
    for pattern in TOOL_LOG_PATTERNS:
        if re.match(pattern, line):
            return True
    # Check banner patterns
    for pattern in KIRO_BANNER_PATTERNS:
        if re.match(pattern, line):
            return True
    return False

def is_kiro_banner_line(line: str) -> bool:
    """Check if line is part of the Kiro ASCII banner."""
    # Banner contains these specific Unicode characters
    banner_chars = set('⢀⣴⣶⣦⡀⠀⣾⣿⠋⠁⠈⠙⡆⢻⢰⣇⡿⣼⠇⢸⣤⣄⠉⠹⣷⣆⣠⠃⢿⢹⣧⠻⠟⢀⢴')
    line_chars = set(line)
    # If more than 30% of unique chars are banner chars, it's banner
    if line_chars and len(line_chars & banner_chars) / len(line_chars) > 0.3:
        return True
    # Box drawing characters
    if re.match(r'^[╭╮╰╯│─\s]+$', line):
        return True
    return False

def filter_tool_logs(text: str) -> str:
    """Remove verbose tool execution logs from output."""
    lines = text.split('\n')
    filtered = [line for line in lines if not is_tool_log_line(line)]
    result = '\n'.join(filtered)
    # Clean up multiple blank lines
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result


@dataclass
class KiroAgentConfig(AgentConfig):
    """Configuration for Kiro agent."""

    model: str = "claude-sonnet-4.5"  # claude-opus-4.5, claude-sonnet-4.5, claude-haiku-4.5
    trust_all_tools: bool = True  # Auto-approve all tools for non-interactive mode
    # Trusted tools (only used if trust_all_tools is False)
    trusted_tools: list = None  # Default set in __post_init__

    def __post_init__(self):
        if self.trusted_tools is None:
            # Trust common tools for coding tasks
            self.trusted_tools = [
                "Read", "Edit", "Write", "Bash", "Glob", "Grep",
                "fs_read", "fs_write", "execute_bash",
                "web_search", "web_fetch",
            ]


class KiroAgent(Agent):
    """Agent that uses kiro-cli for Claude models."""

    def __init__(self, config: KiroAgentConfig) -> None:
        super().__init__(config)
        self._kiro_path = shutil.which("kiro-cli")
        if not self._kiro_path:
            # Check common locations
            import os
            for path in [
                os.path.expanduser("~/.local/bin/kiro-cli"),
                "/usr/local/bin/kiro-cli",
            ]:
                if os.path.exists(path):
                    self._kiro_path = path
                    break

    @property
    def available(self) -> bool:
        """Check if kiro-cli is available."""
        return self._kiro_path is not None

    def get_system_prompt(self, context: dict[str, Any] | None = None) -> tuple[str, list]:
        """Get system prompt with Kiro-specific additions."""
        prompt, matched_skills = super().get_system_prompt(context)
        
        # Add Canvas/Tool instructions since kiro-cli can't see Python tools natively
        tool_instructions = """
## Tool Usage
You have access to a specialized 'Canvas' tool for creating visual artifacts like flowcharts, diagrams, code blocks, and forms.
To use the Canvas tool (or any other tool), you MUST output a tool block using this EXACT format:

<tool_code>
{
  "tool": "canvas",
  "action": "create",
  "artifact_type": "diagram",
  "title": "Flowchart Title",
  "content": "mermaid code for flowchart..."
}
</tool_code>

Supported artifact_types: code, preview (html), form, chart, diagram (mermaid), table, diff, terminal, markdown.
For 'diagram' type, put Mermaid syntax in 'content'.
For 'code' type, put source code in 'content' and specify 'language'.

## Thinking Process
You have a "thinking" capability. Use it to plan and reason before answering complex questions or writing code.
Wrap your thought process in `<thinking>` tags. This content will be shown as a process indicator to the user but not in the final answer.

<thinking>
Analyzing the request...
1. Check file X
2. Plan modification Y
</thinking>
"""
        return prompt + tool_instructions, matched_skills

    async def chat(
        self,
        messages: list,
        context: dict[str, Any] | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> AsyncIterator[str]:
        """Chat using kiro-cli.

        Args:
            messages: List of conversation messages
            context: Optional context dict (workspace, memory, files, etc.)
            model_override: Optional model to use instead of default
            temperature_override: Ignored (kiro-cli doesn't support this)
            max_tokens_override: Ignored (kiro-cli doesn't support this)
        """
        if not self.available:
            yield "❌ kiro-cli not found. Install it with:\n"
            yield "```\ncurl -fsSL https://cli.kiro.dev/install | bash\n```\n"
            yield "Then run `kiro-cli login` to authenticate."
            return

        # Build the prompt from messages
        prompt_parts = []

        # Add system prompt
        system_prompt = self.get_system_prompt(context)
        if system_prompt:
            prompt_parts.append(f"System: {system_prompt}\n")

        # Add conversation history
        for msg in messages:
            role = msg.role.capitalize()
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            prompt_parts.append(f"{role}: {content}")

        full_prompt = "\n\n".join(prompt_parts)

        # Use model_override if provided, otherwise fall back to settings or config
        from app.config import settings
        model = model_override or settings.default_model or self.config.model or "claude-sonnet-4.5"

        # Log which model is being used
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"KiroAgent using model: {model} (settings.default_model={settings.default_model})")

        # Build kiro-cli command
        cmd = [
            self._kiro_path,
            "chat",
            "--no-interactive",
            "--wrap", "never",
        ]

        # Add model
        if model:
            cmd.extend(["--model", model])

        # Add tool trust settings
        if hasattr(self.config, 'trust_all_tools') and self.config.trust_all_tools:
            cmd.append("--trust-all-tools")
        elif hasattr(self.config, 'trusted_tools') and self.config.trusted_tools:
            # Trust only specific tools (read-only by default)
            tools_list = ",".join(self.config.trusted_tools)
            cmd.extend(["--trust-tools", tools_list])

        # Add the prompt
        cmd.append(full_prompt)

        # Run kiro-cli and stream output
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Running kiro-cli: {' '.join(cmd[:3])}...")  # Log command (not full prompt)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Stream stdout with line-based filtering
            # Stream stdout with line-based filtering AND block parsing
            buffer = ""
            total_received = 0
            lines_yielded = 0
            lines_filtered = 0
            in_banner = True
            
            # State for block parsing
            block_buffer = ""  # Accumulates content across lines for parsing (tool/thinking)
            current_block_type = None  # 'tool' or 'thinking' or None
            
            while True:
                chunk = await process.stdout.read(512)
                
                if not chunk:
                    # Flush remaining buffer by forcing a newline
                    if buffer:
                        buffer += '\n'
                    else:
                        break

                if chunk:
                    text = chunk.decode("utf-8", errors="replace")
                    buffer += text
                    total_received += len(text)

                # Process complete lines
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    
                    # 1. Clean the line (ANSI strip)
                    line_clean = ANSI_ESCAPE.sub('', line)
                    cleaned = line_clean.strip()

                    # 2. Filter noise (banners, logs) - ONLY if not inside a block (to avoid filtering useful json/thought content)
                    # Although tools might output logs, we generally want to hide them.
                    # But if we are in a <tool_code> block, we want the JSON as-is.
                    
                    if not current_block_type:
                        # Skip empty lines at start
                        if not cleaned and in_banner:
                            lines_filtered += 1
                            continue
                        # Check for banner
                        if is_kiro_banner_line(cleaned):
                            lines_filtered += 1
                            continue
                        # Check for tool logs
                        if is_tool_log_line(cleaned):
                            lines_filtered += 1
                            continue
                        
                        in_banner = False
                        
                        # Strip leading >
                        if cleaned.startswith('> '):
                            cleaned = cleaned[2:]
                            line_clean = cleaned # Use cleaned for processing

                    # 3. Block Detection State Machine
                    
                    # Check for start tags
                    if not current_block_type:
                        if '<tool_code>' in line_clean:
                            current_block_type = 'tool'
                            # Start buffering tool code (strip the tag if on same line, or keep it?)
                            # Simplest: extract what is after the tag
                            start_idx = line_clean.find('<tool_code>') + 11
                            block_buffer = line_clean[start_idx:] + "\n"
                            
                            # Check if it ends on same line
                            if '</tool_code>' in block_buffer:
                                end_idx = block_buffer.find('</tool_code>')
                                json_str = block_buffer[:end_idx]
                                
                                # Process Tool Execution immediately
                                try:
                                    tool_call = json.loads(json_str)
                                    tool_name = tool_call.pop("tool", "canvas")
                                    yield f"\n\n🔧 **{tool_name}** (executing)...\n"
                                    result = await tool_registry.execute(tool_name, **tool_call)
                                    if result.success:
                                        yield f"```\n{result.output[:1000]}\n```\n"
                                        if result.data and result.data.get("action") == "canvas_create":
                                            artifact_json = json.dumps(result.data["artifact"])
                                            yield f"__CANVAS_CREATE__{artifact_json}__CANVAS_END__"
                                    else:
                                        yield f"❌ Tool Error: {result.error}\n"
                                except Exception as e:
                                    yield f"⚠️ Tool Parse Error: {e}\n"
                                
                                # Reset
                                current_block_type = None
                                block_buffer = ""
                            continue # Don't yield this line to user
                        
                        elif '<thinking>' in line_clean:
                            current_block_type = 'thinking'
                            yield "__THINKING_START__"
                            # If there is content after tag on same line, that counts as thought
                            # But we hide it.
                            
                            # Check for immediate close
                            if '</thinking>' in line_clean:
                                yield "__THINKING_END__"
                                current_block_type = None
                            continue # Hide line

                    # Check for end tags if inside block
                    elif current_block_type == 'tool':
                        if '</tool_code>' in line_clean:
                            # End of tool block found
                            end_idx = line_clean.find('</tool_code>')
                            block_buffer += line_clean[:end_idx]
                            
                            # Process Accumulated Tool Execution
                            try:
                                json_str = block_buffer.strip()
                                tool_call = json.loads(json_str)
                                tool_name = tool_call.pop("tool", "canvas")
                                yield f"\n\n🔧 **{tool_name}** (executing)...\n"
                                result = await tool_registry.execute(tool_name, **tool_call)
                                if result.success:
                                    yield f"```\n{result.output[:1000]}\n```\n"
                                    if result.data and result.data.get("action") == "canvas_create":
                                        artifact_json = json.dumps(result.data["artifact"])
                                        yield f"__CANVAS_CREATE__{artifact_json}__CANVAS_END__"
                                else:
                                    yield f"❌ Tool Error: {result.error}\n"
                            except Exception as e:
                                yield f"⚠️ Tool Parse Error: {e}\n"
                            
                            current_block_type = None
                            block_buffer = ""
                        else:
                            block_buffer += line_clean + "\n"
                        continue # Don't yield tool code lines to user

                    elif current_block_type == 'thinking':
                        if '</thinking>' in line_clean:
                            yield "__THINKING_END__"
                            current_block_type = None
                        # Else: Swallow content (don't yield)
                        continue

                    # 4. Normal Output Yielding (if not in block and not filtered)
                    if cleaned:
                        yield line_clean + '\n'
                        lines_yielded += 1
                    else:
                        lines_filtered += 1

            # Wait for completion
            await process.wait()

            logger.info(f"Kiro-cli finished: received={total_received} bytes, yielded={lines_yielded} lines, filtered={lines_filtered} lines, returncode={process.returncode}")

            # Check for errors
            if process.returncode != 0:
                stderr = await process.stderr.read()
                error_text = stderr.decode("utf-8", errors="replace")
                logger.error(f"Kiro-cli error: {error_text}")
                if "login" in error_text.lower() or "auth" in error_text.lower():
                    yield "\n\n❌ Kiro CLI not authenticated. Run `kiro-cli login` first."
                else:
                    yield f"\n\n❌ Kiro CLI error: {error_text}"
            elif total_received == 0:
                logger.warning("Kiro-cli returned no output")
                yield "\n\n⚠️ No response from Kiro. The model may be overloaded or the request timed out."

        except Exception as e:
            logger.exception(f"Kiro-cli exception: {e}")
            yield f"\n\n❌ Error running kiro-cli: {e}"


def create_kiro_agent(
    agent_id: str = "kiro",
    name: str = "Kiro",
    description: str = "Claude via Kiro CLI (AWS-hosted)",
    model: str = "claude-sonnet",
    system_prompt: str = "",
    **kwargs: Any,
) -> KiroAgent:
    """Factory function to create a Kiro agent."""
    config = KiroAgentConfig(
        id=agent_id,
        name=name,
        description=description,
        icon="🦜",
        model=model,
        system_prompt=system_prompt,
        **kwargs,
    )
    return KiroAgent(config)

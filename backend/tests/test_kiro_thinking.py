
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.kiro import KiroAgent, KiroAgentConfig

@pytest.mark.asyncio
async def test_kiro_agent_thinking_tags_parsed():
    """Test that KiroAgent correctly parses <thinking> tags into events."""
    
    config = KiroAgentConfig(id="test", name="Test", description="Desc")
    agent = KiroAgent(config)
    
    with patch("shutil.which", return_value="/bin/true"):
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=None)
        
        # Simulating Kiro outputting thinking tags
        chunks = [
            b"Hello\n",
            b"<thinking>\nThis is my inner thought\n</thinking>\n",
            b"World"
        ]
        
        async def mock_read(n):
            if chunks:
                return chunks.pop(0)
            return b""
            
        mock_process.stdout.read = AsyncMock(side_effect=mock_read)
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = [MagicMock(role="user", content="hi")]
            
            output = []
            async for chunk in agent.chat(messages):
                output.append(chunk)
            
            full_output = "".join(output)
            
            # EXPECTATION (FIXED):
            # Should have START event
            assert "__THINKING_START__" in full_output
            # Should have END event
            assert "__THINKING_END__" in full_output
            # Inner thought content should be hidden (swallowed)
            assert "This is my inner thought" not in full_output
            # Normal content should be present
            assert "Hello" in full_output
            assert "World" in full_output

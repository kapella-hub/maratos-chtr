
import pytest
import shutil
from unittest.mock import AsyncMock, MagicMock, patch
from app.agents.kiro import KiroAgent, KiroAgentConfig
from app.tools.base import registry

@pytest.mark.asyncio
async def test_kiro_agent_parse_canvas_tool():
    """Test that KiroAgent correctly parses <tool_code> blocks from kiro-cli output."""
    
    # Mock configuration
    config = KiroAgentConfig(
        id="test-kiro",
        name="Test Kiro",
        description="Test Agent",
        model="claude-test"
    )
    
    # Initialize agent
    agent = KiroAgent(config)
    
    # Mock shutil.which to ensure agent.available is True
    # (Since we are mocking the subprocess anyway, this is just to pass the check)
    with patch("shutil.which", return_value="/fake/path/kiro-cli"):
        
        # Mock the subprocess
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=None)
        
        # Simulate output from kiro-cli containing a tool block
        # We need to simulate the yield behavior of stdout.read()
        # The agent reads in chunks.
        
        tool_json = '{"tool": "canvas", "action": "create", "artifact_type": "diagram", "title": "Test Flowchart", "content": "graph TD; A-->B;"}'
        output_chunks = [
            b"Here is your flowchart:\n",
            f"<tool_code>{tool_json}</tool_code>\n".encode("utf-8"),
            b"Done."
        ]
        
        async def mock_read(n):
            if output_chunks:
                return output_chunks.pop(0)
            return b""
            
        mock_process.stdout.read = AsyncMock(side_effect=mock_read)
        
        # Mock asyncio.create_subprocess_exec
        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            
            # Mock the tool registry to capture execution
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value=MagicMock(success=True, output="Canvas created", data={"action": "canvas_create", "artifact": {"id": "123"}}))
            
            # We need to patch the registry used IN the agent module
            # Since we imported registry from app.tools.base, and the agent uses app.tools.base.registry (via import)
            # checking the import in kiro.py: "from app.tools.base import registry as tool_registry"
            
            with patch("app.agents.kiro.tool_registry") as mock_registry:
                mock_registry.execute = AsyncMock(return_value=MagicMock(success=True, output="Canvas created", data={"action": "canvas_create", "artifact": {"id": "123"}}))
                
                # Run chat
                messages = [MagicMock(role="user", content="make a chart")]
                response_gen = agent.chat(messages)
                
                output = []
                async for chunk in response_gen:
                    output.append(chunk)
                
                # Join output to check content
                full_output = "".join(output)
                
                # Check that tool execution logic was triggered
                # 1. Check if registry.execute was called with correct args
                mock_registry.execute.assert_called_with(
                    "canvas",
                    action="create",
                    artifact_type="diagram",
                    title="Test Flowchart",
                    content="graph TD; A-->B;"
                )
                
                # 2. Check if the special marker is in the output
                assert "__CANVAS_CREATE__" in full_output
                assert "__CANVAS_END__" in full_output
                assert "Here is your flowchart" in full_output


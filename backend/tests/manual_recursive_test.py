
import asyncio
import json
from app.thinking.manager import ThinkingManager, ThinkingLevel, ThinkingStepType
from app.thinking.models import ThinkingBlockStatus

async def test_recursive_flow():
    manager = ThinkingManager()
    
    # 1. Create Session
    session = await manager.create_session(message_id="test_msg", level=ThinkingLevel.MEDIUM)
    print(f"Session Created: {session.id}")
    
    # 2. Simulate Stream with Tool Call
    stream_content = [
        "__THINKING_START__",
        "[ANALYSIS] I need to check the file system.\n",
        "[TOOL_CALL] list_dir path='.'\n",
        "__THINKING_END__",
    ]
    
    async def mock_stream():
        for chunk in stream_content:
            yield chunk

    print("\nProcessing Stream...")
    async for event in manager.stream_thinking_events(session, mock_stream()):
        print(f"Event: {event.get('type')}")
        if event.get('type') == 'thinking_paused':
            print("  -> Block Paused!")
            block = event.get('block')
            if block['status'] == 'paused_for_tool':
                 print("  -> Status Correct: paused_for_tool")
            else:
                 print(f"  -> ERROR: Status is {block['status']}")

    # Verify Session State
    if session.blocks:
        last_block = session.blocks[-1]
        print(f"\nFinal Block Status: {last_block.status.value}")
        if last_block.status == ThinkingBlockStatus.PAUSED_FOR_TOOL:
            print("✓ SUCCESS: Block paused for tool")
        else:
             print("✗ FAILED: Block not paused")
    else:
        print("✗ FAILED: No blocks found")

if __name__ == "__main__":
    asyncio.run(test_recursive_flow())

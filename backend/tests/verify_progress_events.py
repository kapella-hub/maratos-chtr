
import json
import logging
from app.api.chat import _workflow_event_to_progress

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_workflow_state():
    # Test coding state
    event = 'data: {"type": "workflow_state", "state": "coding", "fix_cycles": 0}\n\n'
    result = _workflow_event_to_progress(event)
    assert result == {
        "type": "status_update",
        "status": "coding",
        "message": "👨‍💻 Coding"
    }, f"Failed coding state: {result}"
    print("✓ Coding state passed")

    # Test unknown state
    event = 'data: {"type": "workflow_state", "state": "unknown"}\n\n'
    result = _workflow_event_to_progress(event)
    assert result is None, f"Failed unknown state: {result}"
    print("✓ Unknown state passed")

def test_agent_completed():
    event = 'data: {"type": "agent_completed", "status": "done", "artifacts": ["file1.py"]}\n\n'
    result = _workflow_event_to_progress(event)
    assert result == {
        "type": "status_update",
        "status": "completed",
        "message": "✓ Agent completed task"
    }, f"Failed agent completed: {result}"
    print("✓ Agent completed passed")

def test_gate_result():
    event = 'data: {"type": "gate_result", "gate": "tester", "passed": true, "tests_run": 5, "tests_passed": 5}\n\n'
    result = _workflow_event_to_progress(event)
    assert result == {
        "type": "status_update",
        "status": "testing",
        "message": "✓ Tests: 5/5 passed"
    }, f"Failed gate result: {result}"
    print("✓ Gate result passed")

def test_workflow_completed():
    event = 'data: {"type": "workflow_completed"}\n\n'
    result = _workflow_event_to_progress(event)
    assert result == {
        "type": "status_update",
        "status": "completed",
        "message": "✓ Workflow completed"
    }, f"Failed workflow completed: {result}"
    print("✓ Workflow completed passed")

if __name__ == "__main__":
    try:
        test_workflow_state()
        test_agent_completed()
        test_gate_result()
        test_workflow_completed()
        print("\nAll tests passed!")
    except ImportError:
        print("Could not import app.api.chat. Run this from backend root.")
    except Exception as e:
        print(f"\nTest failed: {e}")
        exit(1)

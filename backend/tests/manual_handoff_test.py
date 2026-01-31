
from app.collaboration.handoff import HandoffManager, Handoff

def test_handoff():
    manager = HandoffManager()
    handoff = manager.create_handoff(
        from_agent="coder",
        to_agent="tester",
        task_description="Fix login bug",
        files_modified=["src/login.ts"],
        key_decisions=["Used JWT"]
    )
    
    # Serialize
    json_str = manager.serialize(handoff)
    print(f"Serialized Handoff:\n{json_str}")
    
    # Deserialize
    reloaded = manager.deserialize(json_str)
    
    assert reloaded.id == handoff.id
    assert reloaded.context.files_modified == ["src/login.ts"]
    print("\n✓ Verification Successful")

if __name__ == "__main__":
    test_handoff()


from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel

class StateDiff(BaseModel):
    timestamp: datetime
    entity_type: str  # "task", "project", "run"
    entity_id: str
    change_type: str  # "status_change", "new_item", "modification"
    field: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    description: str

class DiffService:
    """
    Calculates semantic differences between state snapshots.
    """
    
    @staticmethod
    def diff_tasks(old_task: Dict[str, Any], new_task: Dict[str, Any]) -> List[StateDiff]:
        diffs = []
        task_id = new_task.get("id")
        timestamp = datetime.now()
        
        # Check status change
        if old_task.get("status") != new_task.get("status"):
            diffs.append(StateDiff(
                timestamp=timestamp,
                entity_type="task",
                entity_id=task_id,
                change_type="status_change",
                field="status",
                old_value=old_task.get("status"),
                new_value=new_task.get("status"),
                description=f"Task '{new_task.get('title')}' moved from {old_task.get('status')} to {new_task.get('status')}"
            ))
            
        # Check for new iterations (attempts)
        old_attempts = len(old_task.get("iterations", []))
        new_attempts = len(new_task.get("iterations", []))
        if new_attempts > old_attempts:
             diffs.append(StateDiff(
                timestamp=timestamp,
                entity_type="task",
                entity_id=task_id,
                change_type="modification",
                field="iterations",
                old_value=old_attempts,
                new_value=new_attempts,
                description=f"Task '{new_task.get('title')}' started attempt #{new_attempts}"
            ))
            
        return diffs

    @staticmethod
    def compare_runs(old_run: Dict[str, Any], new_run: Dict[str, Any]) -> List[StateDiff]:
        diffs = []
        run_id = new_run.get("id")
        timestamp = datetime.now()
        
        # Status
        if old_run.get("status") != new_run.get("status"):
            diffs.append(StateDiff(
                timestamp=timestamp,
                entity_type="run",
                entity_id=run_id,
                change_type="status_change",
                field="status",
                old_value=old_run.get("status"),
                new_value=new_run.get("status"),
                description=f"Project status changed to {new_run.get('status')}"
            ))
            
        return diffs

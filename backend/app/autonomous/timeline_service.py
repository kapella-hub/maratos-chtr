
from typing import List, Any, Dict
from datetime import datetime
from pydantic import BaseModel
from app.autonomous.repositories import RunRepository, TaskRepository, LogRepository

class TimelineEvent(BaseModel):
    id: str
    timestamp: datetime
    type: str # "task_created", "task_completed", "run_started", "log", "signal"
    message: str
    significance: str # "high", "medium", "low"
    metadata: Dict[str, Any] = {}

class TimelineService:
    """
    Aggregates disparate events into a cohesive timeline.
    """
    
    @staticmethod
    async def get_project_timeline(run_id: str) -> List[TimelineEvent]:
        timeline = []
        
        # 1. Run Events
        run = await RunRepository.get(run_id)
        if run:
            # Note: Created_at isn't on Run model yet in this mock, using current guess or we'd need to add it.
            # Assuming Run model has created_at based on typical patterns, but checking schema... 
            # Reviewing viewed code: OrchestrationRun has completed_at, paused_at. 
            # We might need to rely on the "started" event log if created_at is missing, or add it.
            # For now, let's use what we have or infer.
            pass

        # 2. Task Events
        tasks = await TaskRepository.get_by_run(run_id)
        for task in tasks:
            # Task Created (Low significance, inferred)
            # We don't have created_at on task explicitly in the viewed snippet, 
            # checking OrchestrationTask model again... 
            # It has `completed_at`.
            
            if task.completed_at:
                timeline.append(TimelineEvent(
                     id=f"task_complete_{task.id}",
                     timestamp=task.completed_at,
                     type="task_completed",
                     message=f"Task '{task.title}' completed",
                     significance="high",
                     metadata={"task_id": task.id, "result": str(task.result)}
                ))
                
            if task.error:
                # We assume failure happened around completed_at or now if null
                ts = task.completed_at or datetime.now()
                timeline.append(TimelineEvent(
                     id=f"task_fail_{task.id}",
                     timestamp=ts,
                     type="task_failed",
                     message=f"Task '{task.title}' failed: {task.error[:50]}...",
                     significance="high",
                     metadata={"task_id": task.id, "error": task.error}
                ))

        # 3. Sort by timestamp
        timeline.sort(key=lambda x: x.timestamp)
        return timeline

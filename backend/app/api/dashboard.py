
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime

from app.autonomous.diff_service import DiffService, StateDiff
from app.autonomous.signal_service import SignalService, Signal
from app.autonomous.timeline_service import TimelineService, TimelineEvent
from app.autonomous.repositories import RunRepository, TaskRepository

router = APIRouter(prefix="/projects/{run_id}", tags=["dashboard"])

@router.get("/diff", response_model=List[StateDiff])
async def get_project_diff(run_id: str, since: Optional[datetime] = None):
    """
    Get state changes for the project.
    TODO: In a real implementation, we would need to store snapshots to compare against.
    For now, this is a placeholder that would calculate diffs if we had history.
    """
    # Mock implementation for initial version
    return []

@router.get("/signals", response_model=List[Signal])
async def get_project_signals(run_id: str):
    """
    Extract actionable signals from project logs/tasks.
    """
    tasks = await TaskRepository.get_by_run(run_id)
    all_signals = []
    
    for task in tasks:
        # Extract from task title/description
        signals = SignalService.extract_signals(f"{task.title}\n{task.description}", source="task_def")
        all_signals.extend(signals)
        
        # Extract from result if available
        if task.result:
            result_signals = SignalService.extract_signals(task.result, source="task_result")
            all_signals.extend(result_signals)
            
        # Extract from error if available
        if task.error:
            error_signals = SignalService.extract_signals(task.error, source="task_error")
            all_signals.extend(error_signals)
            
    return all_signals

@router.get("/timeline", response_model=List[TimelineEvent])
async def get_project_timeline(run_id: str):
    """
    Get chronological timeline of project events.
    """
    return await TimelineService.get_project_timeline(run_id)

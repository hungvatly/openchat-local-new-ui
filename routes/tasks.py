import asyncio
import uuid
import json
from typing import Dict, Any

from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from core.task_mode.task_runner import TaskSession

router = APIRouter()

# Global dict to store active tasks
# In production, you'd cap the size of this or clean it up.
active_tasks: Dict[str, TaskSession] = {}

@router.post("/api/task/start")
async def start_task(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    folder_path = body.get("folder_path")
    task_desc = body.get("task")
    
    if not folder_path or not task_desc:
        return JSONResponse({"error": "folder_path and task fields are required"}, status_code=400)
        
    task_id = str(uuid.uuid4())
    session = TaskSession(task_id, folder_path, task_desc)
    active_tasks[task_id] = session
    
    # Run the sequence loop in background tasks
    # Wait, Starlette BackgroundTasks do not return until the endpoint finishes.
    # We want it to run as a concurrent Task immediately because of SSE streams.
    asyncio.create_task(session.run())
    
    return {"task_id": task_id}

@router.get("/api/task/{task_id}/stream")
async def stream_task(task_id: str):
    if task_id not in active_tasks:
        return JSONResponse({"error": "Task not found"}, status_code=404)
        
    session = active_tasks[task_id]
    
    async def event_generator():
        try:
            while session.is_running or not session.event_queue.empty():
                try:
                    # Wait for an event with timeout so we don't block forever if it hangs
                    event = await asyncio.wait_for(session.event_queue.get(), timeout=2.0)
                    yield {"data": json.dumps(event)}
                    session.event_queue.task_done()
                    if event.get("event") == "closed":
                        break
                except asyncio.TimeoutError:
                    if not session.is_running and session.event_queue.empty():
                        break
                    # Send a ping to keep connection alive
                    yield {"event": "ping", "data": ""}
        finally:
            if not session.is_running:
                # Cleanup
                active_tasks.pop(task_id, None)

    return EventSourceResponse(event_generator())

@router.post("/api/task/{task_id}/approve")
async def approve_task(task_id: str, request: Request):
    if task_id not in active_tasks:
        return JSONResponse({"error": "Task not found"}, status_code=404)
        
    body = await request.json()
    decision = body.get("decision")
    if decision not in ["approve", "skip"]:
        return JSONResponse({"error": "Decision must be 'approve' or 'skip'"}, status_code=400)
        
    session = active_tasks[task_id]
    # Feed decision to unblock the execution cycle
    session.handle_approval(decision)
    return {"status": "ok"}

@router.post("/api/task/{task_id}/stop")
def stop_task(task_id: str):
    if task_id not in active_tasks:
        return JSONResponse({"error": "Task not found"}, status_code=404)
        
    session = active_tasks[task_id]
    session.stop()
    return {"status": "stopped"}

@router.get("/api/task/{task_id}/status")
def status_task(task_id: str):
    if task_id not in active_tasks:
        return JSONResponse({"error": "Task not found"}, status_code=404)
        
    session = active_tasks[task_id]
    return {
        "task_id": session.task_id,
        "folder": session.folder_path,
        "is_running": session.is_running,
        "steps_completed": session.step_count,
        "history": session.action_history
    }

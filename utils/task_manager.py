import uuid
import threading
from typing import Dict, Any, Callable

class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}

    def start_task(self, name: str, target: Callable, *args, **kwargs) -> str:
        """
        Starts a background task and returns a task_id.
        The target function must accept an optional `task_id` kwarg if it wants to update progress,
        or we pass a `progress_callback` to it.
        """
        task_id = uuid.uuid4().hex
        self.tasks[task_id] = {
            "name": name,
            "status": "running",
            "progress": 0,
            "total": 0,
            "message": "Starting...",
            "result": None,
            "error": None
        }
        
        def progress_callback(current: int, total: int, message: str):
            self.update_task(task_id, progress=current, total=total, message=message)
            
        # We inject progress_callback into kwargs
        kwargs['progress_callback'] = progress_callback

        def wrapper():
            try:
                res = target(*args, **kwargs)
                self.tasks[task_id]["status"] = "completed"
                self.tasks[task_id]["result"] = res
                self.tasks[task_id]["progress"] = self.tasks[task_id]["total"]
            except Exception as e:
                self.tasks[task_id]["status"] = "error"
                self.tasks[task_id]["error"] = str(e)
                
        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
        return task_id

    def update_task(self, task_id: str, progress: int = None, total: int = None, message: str = None):
        """Update progress metrics for a task."""
        if task_id not in self.tasks:
            return
        if progress is not None:
            self.tasks[task_id]["progress"] = progress
        if total is not None:
            self.tasks[task_id]["total"] = total
        if message is not None:
            self.tasks[task_id]["message"] = message

    def get_task(self, task_id: str) -> Dict[str, Any]:
        """Fetch the current status of a task."""
        return self.tasks.get(task_id)

# Global instance
task_manager = TaskManager()

import asyncio
import json
import re
from typing import Dict, Any, List

from .folder_scanner import scan_folder
from .history_manager import format_history
from .action_executor import execute_action
from utils.local_llm import local_llm

SYSTEM_PROMPT = """You are a file task assistant. You help users organize, rename, sort, summarize, and manage files in a folder.

You work ONE STEP AT A TIME. Each time you are called, you must decide the SINGLE next action to take.

You must respond with ONLY a valid JSON object. No explanation, no markdown, no extra text.

The JSON must have this exact structure:
{
  "thinking": "Brief explanation of why this is the next step",
  "type": "ACTION_TYPE",
  "params": { ... },
  "needs_approval": true/false,
  "progress_message": "Human-readable description of what this step does"
}

Available action types:

1. SCAN_FILE — Read a file's content or metadata
   params: { "filename": "example.txt", "read_mode": "text" | "metadata_only" }

2. CREATE_FOLDER — Create a new subfolder
   params: { "folder_name": "subfolder_name" }

3. MOVE_FILE — Move a file to a different location within the working folder
   params: { "filename": "old_name.txt", "destination": "subfolder/old_name.txt" }

4. RENAME_FILE — Rename a file
   params: { "filename": "old_name.txt", "new_name": "new_name.txt" }

5. COPY_FILE — Copy a file
   params: { "filename": "source.txt", "destination": "backup/source.txt" }

6. DELETE_FILE — Delete a file (ALWAYS set needs_approval: true)
   params: { "filename": "unwanted.txt" }

7. WRITE_FILE — Create or overwrite a file with new content
   params: { "filename": "summary.txt", "content": "text content here" }

8. APPEND_FILE — Add content to the end of an existing file
   params: { "filename": "log.txt", "content": "new line to add" }

9. DONE — Task is complete, no more actions needed
   params: { "summary": "Brief summary of everything that was done" }

Rules:
- ALWAYS set needs_approval: true for DELETE_FILE, WRITE_FILE, and MOVE_FILE actions
- SCAN_FILE does not need approval (it's read-only)
- CREATE_FOLDER does not need approval
- RENAME_FILE needs approval
- Never access files outside the working folder
- If you're unsure what to do next, use SCAN_FILE to inspect a file before acting on it
- If the task seems complete, respond with DONE
- Never invent filenames — only reference files that appear in the folder state
"""

def extract_json(raw_str: str) -> Dict[str, Any]:
    """Attempt to parse JSON from an LLM response safely stringifying it."""
    # Find anything matching JSON bounds
    # Strip markdown code blocks
    s = re.sub(r'```json\s*', '', raw_str)
    s = re.sub(r'```', '', s)
    s = s.strip()
    
    start_idx = s.find('{')
    end_idx = s.rfind('}')
    if start_idx != -1 and end_idx != -1:
        s = s[start_idx:end_idx+1]
    
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM did not return valid JSON. Context: {s}") from e


class TaskSession:
    def __init__(self, task_id: str, folder_path: str, task_description: str):
        self.task_id = task_id
        self.folder_path = folder_path
        self.task_description = task_description
        self.action_history: List[Dict[str, Any]] = []
        self.is_running = False
        
        # Async Event queue for broadcastingSSE
        self.event_queue = asyncio.Queue()
        
        # Approval gate flag
        self.approval_event = asyncio.Event()
        self.pending_decision = None # 'approve' or 'skip'
        
        self.step_count = 0
        self.max_steps = 50
        
    async def emit(self, event_type: str, data: Dict[str, Any]):
        await self.event_queue.put({"event": event_type, "data": data})

    async def run(self):
        self.is_running = True
        await self.emit("started", {"folder": self.folder_path, "task": self.task_description})
        
        try:
            while self.is_running and self.step_count < self.max_steps:
                self.step_count += 1
                
                # 1. Scan folder
                folder_state = scan_folder(self.folder_path)
                
                # 2. Rebuild History
                history_text = format_history(self.action_history)
                
                # 3. Formulate Prompt
                user_prompt = f"""TASK: {self.task_description}

WORKING FOLDER: {self.folder_path}

CURRENT FOLDER CONTENTS:
{folder_state}

ACTIONS COMPLETED SO FAR:
{history_text}

What is the SINGLE next action? Respond with only the JSON object."""

                # Notify UI that we are "thinking"
                await self.emit("thinking", {"step": self.step_count})

                # 4. Invoke LLM continuously resolving JSON
                llm_response = ""
                async for chunk in local_llm.stream_chat(
                    message=user_prompt,
                    system_prompt=SYSTEM_PROMPT
                ):
                    llm_response += chunk
                    
                # 5. Extract JSON
                try:
                    next_action = extract_json(llm_response)
                except Exception as e:
                    await self.emit("error", {"step": self.step_count, "error": f"JSON parse error: {str(e)}"})
                    break
                    
                a_type = next_action.get("type", "UNKNOWN")
                
                # UI Emit intention
                await self.emit("action_proposed", {
                    "step": self.step_count,
                    "action": next_action
                })
                
                if a_type == "DONE":
                    await self.emit("done", {"summary": next_action.get("params", {}).get("summary", "Done.")})
                    break
                    
                # 6. Check needs_approval
                # Auto-force approval request on destructive
                destructive = {"DELETE_FILE", "WRITE_FILE", "MOVE_FILE", "RENAME_FILE"}
                if next_action.get("needs_approval") or a_type in destructive:
                    await self.emit("awaiting_approval", {"step": self.step_count, "action": next_action})
                    
                    # Pause and wait for API to unblock this
                    self.approval_event.clear()
                    await self.approval_event.wait()
                    
                    if self.pending_decision == "skip":
                        self.action_history.append({"action": next_action, "result": "SKIPPED_BY_USER"})
                        await self.emit("action_skipped", {"step": self.step_count})
                        continue
                        
                # 7. Execute action securely
                await self.emit("executing", {"step": self.step_count, "action": next_action})
                result = execute_action(next_action, self.folder_path)
                
                # 8. Record in history
                self.action_history.append({"action": next_action, "result": result})
                await self.emit("action_completed", {"step": self.step_count, "result": result})

        except Exception as e:
            await self.emit("error", {"step": self.step_count, "error": str(e)})
        finally:
            self.is_running = False
            await self.emit("closed", {})

    def handle_approval(self, decision: str):
        self.pending_decision = decision
        self.approval_event.set()

    def stop(self):
        self.is_running = False
        # If resting on an approval block, unblock gracefully
        self.pending_decision = "skip"
        self.approval_event.set()

import os
import shutil
from pathlib import Path
from typing import Dict, Any

from .content_reader import extract_content

ALLOWED_ACTIONS = {
    "SCAN_FILE", "CREATE_FOLDER", "MOVE_FILE", "RENAME_FILE",
    "COPY_FILE", "DELETE_FILE", "WRITE_FILE", "APPEND_FILE", "DONE"
}

def safe_resolve(working_folder: str, relative_path: str) -> str:
    """
    Resolve a relative path within the working folder.
    Raises ValueError if the resolved path escapes the working folder.
    """
    base = Path(working_folder).resolve()
    target = (base / relative_path).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError(f"Path escapes working folder: {relative_path}")
    return str(target)

def execute_action(action: Dict[str, Any], working_folder: str) -> Dict[str, Any]:
    """
    Execute a single filesystem action within the working folder.
    Returns a result dict with status and details.
    """
    action_type = action.get("type")
    params = action.get("params", {})
    
    if action_type not in ALLOWED_ACTIONS:
        return {"status": "error", "message": f"Unknown action: {action_type}"}
    
    try:
        if action_type == "SCAN_FILE":
            filepath = safe_resolve(working_folder, params["filename"])
            if not os.path.exists(filepath):
                return {"status": "error", "message": f"File not found: {params['filename']}"}
                
            if params.get("read_mode") == "metadata_only":
                stat = os.stat(filepath)
                return {"status": "ok", "size": stat.st_size, "modified": stat.st_mtime}
            else:
                try:
                    content, meta = extract_content(filepath, max_chars=2000)
                    return {"status": "ok", "content": content, "metadata": meta}
                except Exception as e:
                    return {"status": "error", "message": f"Could not extract content: {str(e)}"}
        
        elif action_type == "CREATE_FOLDER":
            folder = safe_resolve(working_folder, params["folder_name"])
            os.makedirs(folder, exist_ok=True)
            return {"status": "ok", "message": f"Created {params['folder_name']}"}
        
        elif action_type == "MOVE_FILE":
            src = safe_resolve(working_folder, params["filename"])
            dst = safe_resolve(working_folder, params["destination"])
            if not os.path.exists(src):
                return {"status": "error", "message": f"Source file not found: {params['filename']}"}
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            return {"status": "ok", "message": f"Moved {params['filename']} to {params['destination']}"}
            
        elif action_type == "COPY_FILE":
            src = safe_resolve(working_folder, params["filename"])
            dst = safe_resolve(working_folder, params["destination"])
            if not os.path.exists(src):
                return {"status": "error", "message": f"Source file not found: {params['filename']}"}
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            return {"status": "ok", "message": f"Copied {params['filename']} to {params['destination']}"}
        
        elif action_type == "RENAME_FILE":
            src = safe_resolve(working_folder, params["filename"])
            dst = safe_resolve(working_folder, params["new_name"])
            if not os.path.exists(src):
                return {"status": "error", "message": f"Source file not found: {params['filename']}"}
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.rename(src, dst)
            return {"status": "ok", "message": f"Renamed {params['filename']} to {params['new_name']}"}
            
        elif action_type == "DELETE_FILE":
            target = safe_resolve(working_folder, params["filename"])
            if not os.path.exists(target):
                return {"status": "error", "message": f"File not found: {params['filename']}"}
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
            return {"status": "ok", "message": f"Deleted {params['filename']}"}
            
        elif action_type == "WRITE_FILE":
            target = safe_resolve(working_folder, params["filename"])
            content = params.get("content", "")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"status": "ok", "message": f"Wrote {len(content)} chars to {params['filename']}"}
            
        elif action_type == "APPEND_FILE":
            target = safe_resolve(working_folder, params["filename"])
            content = params.get("content", "")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'a', encoding='utf-8') as f:
                f.write(content)
            return {"status": "ok", "message": f"Appended {len(content)} chars to {params['filename']}"}
        
        elif action_type == "DONE":
            return {"status": "done", "summary": params.get("summary", "")}
            
    except ValueError as val_e:
        return {"status": "error", "message": str(val_e)}
    except Exception as e:
        return {"status": "error", "message": f"Execution failed: {str(e)}"}
    
    return {"status": "error", "message": "Unhandled action or missing fields"}

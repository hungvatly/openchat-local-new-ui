import json
from typing import List, Dict, Any

def format_history(action_history: List[Dict[str, Any]], max_entries: int = 15) -> str:
    """
    Format action history for the LLM prompt.
    Compacts older entries to save string context based on length, whilst preserving start/end bounds.
    """
    if not action_history:
        return "No actions completed yet."
        
    formatted_lines = []
    
    # helper to format single action
    def format_single(idx: int, entry: Dict[str, Any]) -> str:
        action = entry.get("action", {})
        result = entry.get("result", {})
        
        a_type = action.get("type", "UNKNOWN")
        a_params = action.get("params", {})
        
        param_str = ", ".join([f"{k}='{v}'" for k, v in a_params.items()])
        
        # Format the result block safely
        if isinstance(result, dict):
            status = result.get("status", "")
            if a_type == "SCAN_FILE" and "content" in result:
                content = result["content"]
                # Truncate content in history if it's too long
                if len(content) > 150:
                    content = content[:150] + "...(truncated)"
                res_str = f"status: {status}, extracted: {content}"
            else:
                res_str = ", ".join([f"{k}:{v}" for k, v in result.items()])
        else:
            res_str = str(result)
            
        return f"{idx + 1}. {a_type} {param_str} → {res_str}"
        
    total_len = len(action_history)
    
    if total_len <= max_entries:
        for i, entry in enumerate(action_history):
            formatted_lines.append(format_single(i, entry))
    else:
        # Keep first 3
        for i in range(3):
            formatted_lines.append(format_single(i, action_history[i]))
            
        omitted = total_len - max_entries
        formatted_lines.append(f"... ({omitted} steps omitted for brevity) ...")
        
        # Keep last N
        tail_count = max_entries - 3
        start_tail = total_len - tail_count
        for i in range(start_tail, total_len):
            formatted_lines.append(format_single(i, action_history[i]))
            
    return "\n".join(formatted_lines)

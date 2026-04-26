import os
import mimetypes
from datetime import datetime
from pathlib import Path

def format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def scan_folder(folder_path: str, max_depth: int = 3, max_files: int = 100) -> str:
    """
    Walk the folder and return a tree-style string.
    Limit depth to max_depth. Limit total files to max_files.
    """
    base_path = Path(folder_path).resolve()
    if not base_path.exists():
        return "Folder does not exist."
        
    tree_lines = []
    file_count = 0
    omitted = 0
    
    # We will build a recursive tree builder
    def build_tree(current_path: Path, depth: int, prefix: str = ""):
        nonlocal file_count, omitted
        
        if depth > max_depth:
            tree_lines.append(f"{prefix}└── ... (deeper levels hidden)")
            return
            
        try:
            items = sorted(current_path.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            tree_lines.append(f"{prefix}└── [Permission Denied]")
            return
            
        for i, item in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            
            if item.is_dir():
                # Avoid hidden folders for cleaner output usually, but let's include if tasked
                tree_lines.append(f"{prefix}{connector}{item.name}/")
                new_prefix = prefix + ("    " if is_last else "│   ")
                build_tree(item, depth + 1, new_prefix)
            else:
                if file_count >= max_files:
                    omitted += 1
                    continue
                    
                file_count += 1
                try:
                    stat = item.stat()
                    size_str = format_size(stat.st_size)
                    mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d')
                    mime, _ = mimetypes.guess_type(str(item))
                    mime = mime or "unknown"
                    tree_lines.append(f"{prefix}{connector}{item.name} ({size_str}, {mime}, modified {mtime_str})")
                except Exception:
                    tree_lines.append(f"{prefix}{connector}{item.name} (unreadable)")

    tree_lines.append(f"{base_path.name}/")
    build_tree(base_path, 1)
    
    if omitted > 0:
        tree_lines.append(f"... and {omitted} more files omitted to save context.")
        
    return "\n".join(tree_lines)

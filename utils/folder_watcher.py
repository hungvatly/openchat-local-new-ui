"""
OpenChat Local — Folder Watcher
Monitors directories for new/modified documents and auto-indexes them into per-folder RAG collections.
Each folder gets its own isolated ChromaDB collection.
"""
import os
import time
import json
import hashlib
import asyncio
import threading
from typing import Dict, List, Optional
from pathlib import Path

from config import settings
from utils.document_loader import LOADERS

WATCH_STATE_FILE = os.path.join(settings.CHROMA_PERSIST_DIR, "_watch_state.json")


def _make_collection_name(folder_path: str) -> str:
    """Create a stable, unique ChromaDB collection name from a folder path."""
    h = hashlib.sha256(folder_path.encode()).hexdigest()[:16]
    return f"folder_{h}"


class FolderWatcher:
    def __init__(self):
        # watch_dirs is now a list of dicts: {path, collection_name, label}
        self.watch_dirs: List[Dict] = []
        self.poll_interval: int = int(os.getenv("WATCH_INTERVAL", "3600"))
        self._file_hashes: Dict[str, str] = {}
        self._running = False
        self._thread = None
        self._stats = {"total_watched": 0, "last_scan": None, "auto_indexed": 0}
        self._load_state()

    # ── State persistence ───────────────────

    def _state_path(self) -> str:
        return WATCH_STATE_FILE

    def _load_state(self):
        """Load previously seen file hashes and watch dirs from disk."""
        try:
            with open(self._state_path(), "r") as f:
                data = json.load(f)
                self._file_hashes = data.get("hashes", {})
                raw_dirs = data.get("watch_dirs", [])
                # Migrate old format (list of strings) to new format (list of dicts)
                self.watch_dirs = []
                for d in raw_dirs:
                    if isinstance(d, str):
                        self.watch_dirs.append({
                            "path": d,
                            "collection_name": _make_collection_name(d),
                            "label": os.path.basename(d),
                        })
                    else:
                        self.watch_dirs.append(d)
                self._stats["auto_indexed"] = data.get("auto_indexed", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            self._file_hashes = {}
            self.watch_dirs = []

        default_watch = os.getenv("WATCH_FOLDER", "")
        if default_watch and not any(d["path"] == default_watch for d in self.watch_dirs):
            if os.path.isdir(default_watch):
                self.watch_dirs.append({
                    "path": default_watch,
                    "collection_name": _make_collection_name(default_watch),
                    "label": os.path.basename(default_watch),
                })

    def _save_state(self):
        """Persist file hashes and watch dirs to disk."""
        os.makedirs(os.path.dirname(self._state_path()), exist_ok=True)
        data = {
            "hashes": self._file_hashes,
            "watch_dirs": self.watch_dirs,
            "auto_indexed": self._stats["auto_indexed"],
        }
        with open(self._state_path(), "w") as f:
            json.dump(data, f)

    # ── File hashing ────────────────────────

    def _hash_file(self, filepath: str) -> str:
        try:
            stat = os.stat(filepath)
            h = hashlib.md5()
            h.update(f"{filepath}:{stat.st_size}:{stat.st_mtime}".encode())
            with open(filepath, "rb") as f:
                h.update(f.read(4096))
            return h.hexdigest()
        except OSError:
            return ""

    # ── Scanning ────────────────────────────

    def _get_supported_files(self, folder: str) -> Dict[str, str]:
        supported = set(LOADERS.keys())
        files = {}
        try:
            for root, dirs, filenames in os.walk(folder):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in filenames:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in supported:
                        fpath = os.path.join(root, fname)
                        files[fpath] = self._hash_file(fpath)
        except OSError as e:
            print(f"[Watcher] Error scanning {folder}: {e}")
        return files

    def scan_and_index(self, progress_callback=None) -> Dict:
        """Scan all watch dirs, find new/changed files, and index into per-folder collections."""
        from utils.rag_engine import rag_registry

        new_files = []
        changed_files = []
        all_current = {}

        for folder_info in self.watch_dirs:
            folder = folder_info["path"]
            collection_name = folder_info["collection_name"]
            if not os.path.isdir(folder):
                continue
            current_files = self._get_supported_files(folder)

            for fpath, fhash in current_files.items():
                if fpath not in self._file_hashes:
                    new_files.append((fpath, collection_name))
                elif self._file_hashes[fpath] != fhash:
                    changed_files.append((fpath, collection_name))

            all_current.update(current_files)

        # Also check for files that were "tracked" but never actually indexed (e.g. failed silently)
        for folder_info in self.watch_dirs:
            folder = folder_info["path"]
            collection_name = folder_info["collection_name"]
            if not os.path.isdir(folder):
                continue
            from utils.rag_engine import rag_registry as _rr
            engine = _rr.get_or_create(collection_name)
            stats = engine.get_stats()
            if stats.get("total_chunks", 0) == 0:
                # Collection is empty — force re-index all files in this folder
                current_files = self._get_supported_files(folder)
                for fpath in current_files:
                    entry = (fpath, collection_name)
                    if entry not in new_files and entry not in changed_files:
                        new_files.append(entry)

        # Index new and changed files — only update hash on SUCCESS
        indexed = []
        total_to_index = len(new_files) + len(changed_files)
        for idx, (fpath, collection_name) in enumerate(new_files + changed_files):
            fname = os.path.basename(fpath)
            if progress_callback:
                progress_callback(current=idx, total=total_to_index, message=f"Indexing {idx+1}/{total_to_index}: {fname}")
            try:
                engine = rag_registry.get_or_create(collection_name)
                result = engine.ingest_file(fpath)
                if result.get("status") == "ok":
                    # Only record as indexed if the ingest succeeded
                    self._file_hashes[fpath] = all_current.get(fpath, self._hash_file(fpath))
                    indexed.append({
                        "filename": result.get("filename", os.path.basename(fpath)),
                        "chunks": result.get("chunks", 0),
                        "is_new": (fpath, collection_name) in new_files,
                        "collection_name": collection_name,
                    })
                    self._stats["auto_indexed"] += 1
                else:
                    print(f"[Watcher] Ingest returned non-ok for {fpath}: {result}")
            except Exception as e:
                print(f"[Watcher] Error indexing {fpath}: {e}")
                # Do NOT update _file_hashes — file will be retried on next scan

        # Track files that weren't indexed (already up to date)
        for fpath, fhash in all_current.items():
            if fpath not in self._file_hashes:
                pass  # Will only be marked done if ingest succeeded above
            elif self._file_hashes[fpath] == fhash:
                pass  # Already up to date

        self._stats["total_watched"] = len(all_current)
        self._stats["last_scan"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save_state()

        return {
            "new_files": len(new_files),
            "changed_files": len(changed_files),
            "indexed": indexed,
        }

    # ── Background loop ─────────────────────

    def _poll_loop(self):
        print(f"[Watcher] Started — polling every {self.poll_interval}s")
        print(f"[Watcher] Watching: {[d['path'] for d in self.watch_dirs]}")
        while self._running:
            try:
                result = self.scan_and_index()
                if result["indexed"]:
                    names = [f["filename"] for f in result["indexed"]]
                    print(f"[Watcher] Auto-indexed {len(names)} file(s): {', '.join(names)}")
            except Exception as e:
                print(f"[Watcher] Error in poll loop: {e}")
            time.sleep(self.poll_interval)

    def start(self):
        if self._running or not self.watch_dirs:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    # ── Management ──────────────────────────

    def add_folder(self, folder: str, label: str = None, progress_callback=None) -> Dict:
        """Add a folder to the watch list with its own collection."""
        folder = os.path.abspath(folder)
        if not os.path.isdir(folder):
            return {"status": "error", "message": f"Not a valid directory: {folder}"}

        if any(d["path"] == folder for d in self.watch_dirs):
            return {"status": "ok", "message": "Already watching this folder"}

        collection_name = _make_collection_name(folder)
        folder_label = label or os.path.basename(folder)
        folder_info = {
            "path": folder,
            "collection_name": collection_name,
            "label": folder_label,
        }
        self.watch_dirs.append(folder_info)
        self._save_state()

        # Immediate scan — index ALL files, only record hash on success
        from utils.rag_engine import rag_registry
        engine = rag_registry.get_or_create(collection_name)
        current_files = self._get_supported_files(folder)
        indexed = []
        failed = []
        total_files = len(current_files)
        
        for idx, (fpath, fhash) in enumerate(current_files.items()):
            fname = os.path.basename(fpath)
            if progress_callback:
                progress_callback(current=idx, total=total_files, message=f"Indexing {idx+1}/{total_files}: {fname}")
            try:
                result = engine.ingest_file(fpath)
                if result.get("status") == "ok":
                    # Only mark as seen if ingest succeeded
                    self._file_hashes[fpath] = fhash
                    indexed.append(result.get("filename", os.path.basename(fpath)))
                    self._stats["auto_indexed"] += 1
                else:
                    failed.append(os.path.basename(fpath))
                    print(f"[Watcher] add_folder ingest non-ok for {fpath}: {result}")
            except Exception as e:
                failed.append(os.path.basename(fpath))
                print(f"[Watcher] Error indexing {fpath}: {e}")
                # Do NOT save hash — file will be retried on next scan

        self._stats["total_watched"] = len(current_files)
        self._save_state()

        if not self._running:
            self.start()

        return {
            "status": "ok",
            "folder": folder,
            "label": folder_label,
            "collection_name": collection_name,
            "initial_scan": {
                "indexed": len(indexed),
                "files": indexed,
                "failed": failed,
            },
        }

    def remove_folder(self, folder: str) -> Dict:
        folder = os.path.abspath(folder)
        before = len(self.watch_dirs)
        self.watch_dirs = [d for d in self.watch_dirs if d["path"] != folder]
        if len(self.watch_dirs) == before:
            return {"status": "error", "message": "Folder not in watch list"}
        self._file_hashes = {k: v for k, v in self._file_hashes.items() if not k.startswith(folder)}
        self._save_state()
        return {"status": "ok", "message": f"Stopped watching {folder}"}

    def get_status(self) -> Dict:
        from utils.rag_engine import rag_registry
        folders_info = []
        for d in self.watch_dirs:
            engine = rag_registry.get_or_create(d["collection_name"])
            stats = engine.get_stats()
            folders_info.append({
                "path": d["path"],
                "label": d["label"],
                "collection_name": d["collection_name"],
                "chunk_count": stats["total_chunks"],
            })

        return {
            "running": self._running,
            "watch_dirs": [d["path"] for d in self.watch_dirs],
            "folders": folders_info,
            "poll_interval": self.poll_interval,
            "total_files_tracked": self._stats["total_watched"],
            "total_auto_indexed": self._stats["auto_indexed"],
            "last_scan": self._stats["last_scan"],
        }

    def get_collection_name(self, folder: str) -> Optional[str]:
        """Get the ChromaDB collection name for a given folder path."""
        folder = os.path.abspath(folder)
        for d in self.watch_dirs:
            if d["path"] == folder:
                return d["collection_name"]
        return None


folder_watcher = FolderWatcher()

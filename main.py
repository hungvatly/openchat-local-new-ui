"""
OpenChat Local — Main Server
A cross-platform, open-source local RAG chatbot.
"""
import os
import uuid
import json
import base64
import hashlib
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings, PROFILE, ACTIVE_PROFILE
from utils.local_llm import local_llm, SYSTEM_PROMPT
from utils.web_search import web_search
from utils.folder_watcher import folder_watcher
from utils.ollama_client import ollama_client
from utils.chat_history import chat_history, DEFAULT_USER_ID

# ── Lazy-loaded heavy subsystems (saves 2-4s boot time) ───────────────────────
# Each module is imported on first actual use, not at startup.

class _LazyModule:
    """Transparent proxy that imports a module attribute on first access."""
    def __init__(self, module_path, attr):
        self._module_path = module_path
        self._attr = attr
        self._obj = None
    def _load(self):
        if self._obj is None:
            import importlib
            mod = importlib.import_module(self._module_path)
            self._obj = getattr(mod, self._attr)
    def __getattr__(self, name):
        self._load()
        return getattr(self._obj, name)
    def __call__(self, *args, **kwargs):
        self._load()
        return self._obj(*args, **kwargs)

rag_engine   = _LazyModule("utils.rag_engine", "rag_engine")
rag_registry = _LazyModule("utils.rag_engine", "rag_registry")
extract_and_save_memories = _LazyModule("utils.memory_engine", "extract_and_save_memories")
detect_and_generate = _LazyModule("utils.doc_generator", "detect_and_generate")
generate_docx = _LazyModule("utils.doc_generator", "generate_docx")
generate_pdf  = _LazyModule("utils.doc_generator", "generate_pdf")
generate_xlsx = _LazyModule("utils.doc_generator", "generate_xlsx")

SETTINGS_PATH = os.path.join(settings.CHROMA_PERSIST_DIR, "app_settings.json")

def load_app_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {"theme": "dark"}

def save_app_settings(data: dict):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f)

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
app.mount("/static", StaticFiles(directory="static"), name="static")
os.makedirs("data/generated", exist_ok=True)
app.mount("/files", StaticFiles(directory="data/generated"), name="files")

from routes.tasks import router as task_router
app.include_router(task_router)

templates = Jinja2Templates(directory="templates")

# Subsystems
from utils.mcp_client import mcp_manager
from utils.network_discovery import network_discovery
from utils.screen_context import screen_context
import asyncio

@app.on_event("startup")
async def startup_event():
    import threading
    # Restore saved Ollama URL if set
    app_cfg = load_app_settings()
    saved_ollama_url = app_cfg.get("ollama_url", "")
    if saved_ollama_url:
        ollama_client.base_url = saved_ollama_url

    asyncio.create_task(mcp_manager.start_all())

    # Network broadcast runs in background thread — it does a synchronous DNS probe
    # that would block the event loop if called directly.
    threading.Thread(target=network_discovery.start_broadcasting, daemon=True).start()

    # Auto-start the folder watcher if watch dirs are configured
    if folder_watcher.watch_dirs:
        folder_watcher.start()
        print(f"  [Watcher] Auto-watching {len(folder_watcher.watch_dirs)} folder(s)")
    else:
        print("  [Watcher] No watch folders configured. Set WATCH_FOLDER in .env or add via UI.")

@app.on_event("shutdown")
def shutdown_event():
    mcp_manager.stop_all()
    network_discovery.stop_broadcasting()

# ── API: MCP Servers ────────────────────────────────────────

@app.get("/api/mcp")
def list_mcp_servers():
    return mcp_manager.servers

@app.post("/api/mcp")
async def add_mcp_server(request: Request):
    body = await request.json()
    name = body.get("name")
    command = body.get("command")
    args = body.get("args", [])
    if not name or not command:
        return JSONResponse({"error": "name and command required"}, status_code=400)
    mcp_manager.add_server(name, command, args)
    asyncio.create_task(mcp_manager.start_server(name, command, args))
    return {"status": "success"}

@app.delete("/api/mcp/{name}")
def delete_mcp_server(name: str):
    mcp_manager.remove_server(name)
    return {"status": "success"}

# ── API: OS Screen Capture ────────────────────────────────

@app.get("/api/screen/capture")
def get_screen_capture():
    # Force a capture now
    b64 = screen_context.capture_now()
    if not b64:
        return JSONResponse({"error": "Failed to capture screen"}, status_code=500)
    return {"status": "ok", "base64": f"data:image/jpeg;base64,{b64}"}



# ── Pages ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    response = templates.TemplateResponse(request, "index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ── API: System ────────────────────────────────────────

@app.get("/api/health")
async def health():
    engine_ready = await local_llm.check_health()
    rag_stats = rag_engine.get_stats()

    # Lazy whisper check — avoids import at boot
    def _whisper_available() -> bool:
        try:
            import importlib
            return importlib.util.find_spec("whisper") is not None
        except Exception:
            return False

    return {
        "status": "ok",
        "engine": "local",
        "engine_ready": engine_ready,
        "loaded_model": local_llm.get_loaded_model(),
        "models_dir": settings.MODELS_DIR,
        "rag": rag_stats,
        "profile": PROFILE,
        "recommended_models": ACTIVE_PROFILE["recommended_models"],
        "web_search_enabled": settings.WEB_SEARCH_ENABLED,
        "searxng_configured": bool(settings.SEARXNG_URL),
        "voice_available": _whisper_available(),
        "doc_generation": True,
    }


@app.get("/api/models")
async def list_models():
    models = await local_llm.list_models()
    # Pick a default: prefer the configured DEFAULT_MODEL if it exists in the list,
    # otherwise fall back to the first available model (Ollama or local).
    all_names = [m["name"] for m in models]
    default = settings.DEFAULT_MODEL if settings.DEFAULT_MODEL in all_names else (all_names[0] if all_names else "")
    return {"models": models, "default": default}


@app.post("/api/models/download")
async def download_model(request: Request):
    """Download a model from HuggingFace Hub (GGUF or SafeTensors)."""
    body = await request.json()
    repo_id = body.get("repo_id", "").strip()
    filename = body.get("filename", "").strip()
    fmt = body.get("format", "gguf")  # "gguf" or "safetensors"
    if not repo_id:
        return JSONResponse({"error": "repo_id required"}, status_code=400)
    if fmt == "gguf" and not filename:
        return JSONResponse({"error": "filename required for GGUF downloads"}, status_code=400)
    if fmt == "gguf" and not filename.endswith(".gguf"):
        return JSONResponse({"error": "Only .gguf files are supported for GGUF format"}, status_code=400)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, local_llm.download_model, repo_id, filename, fmt)
    if result.get("status") == "error":
        return JSONResponse(result, status_code=400)
    return result


@app.post("/api/models/import")
async def import_model(request: Request):
    """Import a local GGUF file or SafeTensors directory into the models directory."""
    body = await request.json()
    source_path = body.get("path", "").strip()
    if not source_path:
        return JSONResponse({"error": "path required"}, status_code=400)
    result = local_llm.import_model(source_path)
    if result.get("status") == "error":
        return JSONResponse(result, status_code=400)
    return result


@app.delete("/api/models/{name}")
async def delete_model(name: str):
    result = local_llm.delete_model(name)
    if result.get("status") == "error":
        return JSONResponse(result, status_code=404)
    return result


@app.post("/api/models/load")
async def load_model(request: Request):
    """Explicitly pre-load a model into memory."""
    body = await request.json()
    model_name = body.get("model", "").strip()
    try:
        result = local_llm.load_model(model_name or None)
        return result
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def _write_env_extra_models(extra_dirs: str):
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
    else:
        lines = []
    
    with open(env_path, "w") as f:
        found = False
        for line in lines:
            if line.startswith("EXTRA_MODELS_DIRS="):
                f.write(f"EXTRA_MODELS_DIRS={extra_dirs}\n")
                found = True
            else:
                f.write(line)
        if not found:
            f.write(f"EXTRA_MODELS_DIRS={extra_dirs}\n")
    
    settings.EXTRA_MODELS_DIRS = extra_dirs


@app.get("/api/models/directories")
async def get_model_dirs():
    dirs = [settings.MODELS_DIR]
    if settings.EXTRA_MODELS_DIRS.strip():
        dirs.extend([d.strip() for d in settings.EXTRA_MODELS_DIRS.split(",") if d.strip()])
    return {"directories": list(dict.fromkeys(dirs)), "primary": settings.MODELS_DIR}


@app.post("/api/models/directories")
async def add_model_dir(request: Request):
    body = await request.json()
    new_dir = body.get("path", "").strip()
    if not new_dir or not os.path.isdir(new_dir):
        return JSONResponse({"error": "Invalid or non-existent directory path"}, status_code=400)
    
    current = [d.strip() for d in settings.EXTRA_MODELS_DIRS.split(",") if d.strip()]
    if new_dir in current or new_dir == settings.MODELS_DIR:
        return {"status": "ok", "message": "Already added"}
    
    current.append(new_dir)
    _write_env_extra_models(",".join(current))
    return {"status": "ok", "directories": current}


@app.delete("/api/models/directories")
async def remove_model_dir(request: Request):
    body = await request.json()
    remove_dir = body.get("path", "").strip()
    if remove_dir == settings.MODELS_DIR:
        return JSONResponse({"error": "Cannot remove the primary models directory"}, status_code=400)
        
    current = [d.strip() for d in settings.EXTRA_MODELS_DIRS.split(",") if d.strip()]
    if remove_dir in current:
        current.remove(remove_dir)
        _write_env_extra_models(",".join(current))
    
    return {"status": "ok", "directories": current}


@app.post("/api/models/unload")
async def unload_model():
    local_llm.unload_model()
    return {"status": "ok"}


# ── API: Chat ──────────────────────────────────────────

@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "")
    model = body.get("model", None)
    mode = body.get("mode", "docs")
    parent_id = body.get("parent_id", None)
    history = body.get("history", [])
    conv_id = body.get("conversation_id", None)
    images_b64 = body.get("images", [])  # list of base64 image strings
    session_system_prompt = body.get("session_system_prompt", None)  # per-session override
    user_id = body.get("user_id", DEFAULT_USER_ID)
    is_private = body.get("is_private", False)
    # folder_ids: list of collection names to query (empty = query global docs collection)
    folder_ids: list = body.get("folder_ids", [])
    deep_think = body.get("deep_think", False)

    if not message.strip():
        return JSONResponse({"error": "Empty message"}, status_code=400)

    # Resolve system prompt — priority: session override > global default persona > built-in
    if session_system_prompt and session_system_prompt.strip():
        system_prompt = session_system_prompt.strip()
    else:
        system_prompt = None
        persona = chat_history.get_persona("default")
        if persona and persona.get("prompt"):      # blank prompt → use built-in default
            system_prompt = persona["prompt"]
        if not system_prompt:
            system_prompt = SYSTEM_PROMPT

    # Inject AI memory into system prompt
    memory_block = chat_history.build_memory_prompt(user_id)
    if memory_block:
        system_prompt = memory_block + "\n\n" + (system_prompt or "")

    # Create or reuse conversation
    # Track this BEFORE we create a new id — used for title generation later
    _is_new_conversation = not conv_id
    if not conv_id:
        conv_id = "private_" + uuid.uuid4().hex[:8] if is_private else uuid.uuid4().hex[:12]
        if not is_private:
            chat_history.create_conversation(conv_id, model=model or settings.DEFAULT_MODEL,
                                             persona_id="default", user_id=user_id)

    # Save user message now (pre-stream) so we have the ID for branching
    user_msg_id = None
    if not is_private:
        user_msg_id = chat_history.add_message(conv_id, "user", message, images=",".join(images_b64[:1]) if images_b64 else "", parent_id=parent_id)

    context = ""
    sources = []
    retrieved = []

    if mode == "docs":
        if folder_ids:
            # Query specific folder collection
            context, retrieved = rag_registry.build_context_for_collections(message, folder_ids)
        else:
            # "All Knowledge" — query EVERY known collection (uploaded docs + all watched folders)
            all_ids = ["documents"] + [
                f["collection_name"]
                for f in folder_watcher.get_status().get("folders", [])
            ]
            context, retrieved = rag_registry.build_context_for_collections(message, all_ids)
            # Fallback to global rag_engine if registry doesn't cover "documents"
            if not retrieved:
                retrieved = rag_engine.query(message)
                if retrieved:
                    context = rag_engine.build_context(message)

        if retrieved:
            # Group chunk_indexes by source; also store the collection name for the viewer
            grouped_sources = {}
            for r in retrieved:
                src = r["source"]
                if src not in grouped_sources:
                    grouped_sources[src] = {
                        "source": src,
                        "score": r["score"],
                        "type": "document",
                        "chunk_indexes": [],
                        "collection": r.get("collection", "documents"),
                    }
                if "chunk_index" in r and r["chunk_index"] is not None:
                    grouped_sources[src]["chunk_indexes"].append(r["chunk_index"])
            sources = list(grouped_sources.values())

    elif mode == "web" and settings.WEB_SEARCH_ENABLED:
        search_results = await web_search.search(message, settings.WEB_SEARCH_MAX_RESULTS)
        if search_results:
            web_context_parts = []
            for r in search_results[:3]:
                page_text = await web_search.fetch_page(r["url"], settings.WEB_FETCH_MAX_CHARS)
                if page_text:
                    web_context_parts.append(f"[Source: {r['title']}]\nURL: {r['url']}\n{page_text[:1500]}")
                else:
                    web_context_parts.append(f"[Source: {r['title']}]\nURL: {r['url']}\n{r['snippet']}")
                sources.append({"source": r["title"], "url": r["url"], "type": "web"})
            context = "\n\n---\n\n".join(web_context_parts)

    async def generate():
        full_text = ""
        is_reasoning = model and any(x in model.lower() for x in ["deepseek-r1", "-r1", "reasoning", "think"])
        try:
            if deep_think and not is_reasoning:
                _tok_think_open = json.dumps({"token": "<think>\n"}, ensure_ascii=False)
                _tok_draft_header = json.dumps({"token": "> Drafting initial thought process...\n\n"}, ensure_ascii=False)
                _tok_critique_header = json.dumps({"token": "\n\n> Critiquing draft...\n\n"}, ensure_ascii=False)
                _tok_think_close = json.dumps({"token": "\n</think>\n\n"}, ensure_ascii=False)

                yield f"data: {_tok_think_open}\n\n"

                # Phase 1: Draft
                yield f"data: {_tok_draft_header}\n\n"
                draft_msg = message + "\n\nPlease write a preliminary draft or outline for your answer."
                draft = ""
                async for token in local_llm.stream_chat(
                    message=draft_msg, model=model, context=context, history=history,
                    images=images_b64 if images_b64 else None, system_prompt=system_prompt
                ):
                    draft += token
                    _t = json.dumps({"token": token}, ensure_ascii=False)
                    yield f"data: {_t}\n\n"

                # Phase 2: Critique
                yield f"data: {_tok_critique_header}\n\n"
                critique_msg = (
                    f"User Request: {message}\n\n"
                    f"Draft: {draft}\n\n"
                    "Please critique this draft. What is missing or incorrect?"
                )
                critique = ""
                async for token in local_llm.stream_chat(
                    message=critique_msg, model=model, context=context, history=history,
                    images=images_b64 if images_b64 else None, system_prompt=system_prompt
                ):
                    critique += token
                    _t = json.dumps({"token": token}, ensure_ascii=False)
                    yield f"data: {_t}\n\n"

                yield f"data: {_tok_think_close}\n\n"
                full_text += (
                    "<think>\n> Drafting initial thought process...\n\n"
                    + draft
                    + "\n\n> Critiquing draft...\n\n"
                    + critique
                    + "\n</think>\n\n"
                )

                # Phase 3: Final Output
                final_msg = (
                    f"User Request: {message}\n\n"
                    f"Draft: {draft}\n"
                    f"Critique: {critique}\n\n"
                    "Now provide the final, polished response incorporating the critique above."
                )
                async for token in local_llm.stream_chat(
                    message=final_msg, model=model, context=context, history=history,
                    images=images_b64 if images_b64 else None, system_prompt=system_prompt
                ):
                    full_text += token
                    _t = json.dumps({"token": token}, ensure_ascii=False)
                    yield f"data: {_t}\n\n"

            else:
                async for token in local_llm.stream_chat(
                    message=message, model=model, context=context, history=history,
                    images=images_b64 if images_b64 else None, system_prompt=system_prompt
                ):
                    full_text += token
                    _t = json.dumps({"token": token}, ensure_ascii=False)
                    yield f"data: {_t}\n\n"

        finally:
            # Save AI response & memories if not private
            ai_msg_id = None
            if not is_private and full_text.strip():
                ai_msg_id = chat_history.add_message(conv_id, "assistant", full_text, sources=sources, parent_id=user_msg_id)
                if len(full_text) > 10:
                    asyncio.create_task(extract_and_save_memories(user_id, history, message, full_text))

            # Auto-generate a smart title for the first message of a new conversation.
            # NOTE: We use _is_new_conversation (conv_id absent in request), NOT len(history)==0,
            # because the frontend always includes the current user message in history (len >= 1).
            generated_title = None
            if _is_new_conversation and not is_private and full_text.strip():
                # Use first message + AI reply snippet as context for a better title
                title_context = f"User: {message}\nAssistant: {full_text[:300]}"
                try:
                    # Prefer Ollama title gen when model is an Ollama model
                    _is_ollama_title = False
                    if model:
                        try:
                            from utils.ollama_client import ollama_client
                            if await ollama_client.check_health():
                                ollama_names = {m["name"] for m in await ollama_client.list_models()}
                                if model in ollama_names or ":" in model:
                                    _is_ollama_title = True
                        except Exception:
                            pass
                    if _is_ollama_title:
                        from utils.ollama_client import ollama_client
                        generated_title = await ollama_client.generate_title(title_context, model=model)
                    else:
                        generated_title = await local_llm.generate_title(title_context, model=model)
                except Exception:
                    pass
                # Fallback: first 55 chars of user message
                if not generated_title or generated_title in ("New Chat", ""):
                    generated_title = message[:55].strip()
                # Persist to DB
                chat_history.update_title(conv_id, generated_title)

            # Check if user asked to create a document
            doc_result = detect_and_generate(full_text, message)
            file_info = None
            if doc_result and doc_result.get("status") == "ok":
                file_info = {
                    "filename": doc_result["filename"],
                    "url": f"/files/{doc_result['filename']}",
                    "type": doc_result["type"],
                }

            final_info = {
                "done": True,
                "sources": sources,
                "conversation_id": conv_id,
                "file": file_info,
                "user_message_id": user_msg_id,
                "message_id": ai_msg_id,
                "title": generated_title,   # null when not a new conversation
            }
            yield f"data: {json.dumps(final_info)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── API: Web Search ────────────────────────────────────

@app.post("/api/search")
async def search_web(request: Request):
    body = await request.json()
    query = body.get("query", "")
    if not query.strip():
        return JSONResponse({"error": "Empty query"}, status_code=400)

    results = await web_search.search(query, settings.WEB_SEARCH_MAX_RESULTS)
    return {"results": results, "query": query}


@app.post("/api/search/fetch")
async def fetch_url(request: Request):
    body = await request.json()
    url = body.get("url", "")
    if not url.startswith("http"):
        return JSONResponse({"error": "Invalid URL"}, status_code=400)

    text = await web_search.fetch_page(url, settings.WEB_FETCH_MAX_CHARS)
    if text:
        return {"text": text, "url": url}
    return JSONResponse({"error": "Could not fetch page"}, status_code=400)


# ── API: Documents ─────────────────────────────────────

@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    allowed = {".txt", ".pdf", ".docx", ".md", ".csv", ".xml"}
    if ext not in allowed:
        return JSONResponse(
            {"error": f"Unsupported file type: {ext}. Supported: {', '.join(allowed)}"},
            status_code=400,
        )

    safe_name = os.path.basename(file.filename)
    filepath = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4().hex}_{safe_name}")
    content = await file.read()

    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        return JSONResponse({"error": f"File too large. Max {settings.MAX_FILE_SIZE_MB}MB"}, status_code=400)

    with open(filepath, "wb") as f:
        f.write(content)

    def _upload_task(progress_callback=None):
        if progress_callback:
            progress_callback(current=0, total=1, message=f"Extracting text from {safe_name}...")
        res = rag_engine.ingest_file(filepath)
        if progress_callback:
            progress_callback(current=1, total=1, message=f"Finished indexing {safe_name}")
        return res

    from utils.task_manager import task_manager
    tid = task_manager.start_task(f"Upload {safe_name}", _upload_task)
    return {"status": "processing", "task_id": tid}


@app.post("/api/documents/folder")
async def ingest_folder(request: Request):
    body = await request.json()
    folder = body.get("folder_path", "")
    if not os.path.isdir(folder):
        return JSONResponse({"error": "Invalid folder path"}, status_code=400)

    def _folder_task(progress_callback=None):
        results = rag_engine.ingest_folder(folder)
        return {"status": "ok", "files_processed": len(results), "details": results}

    from utils.task_manager import task_manager
    tid = task_manager.start_task(f"Ingest Folder {os.path.basename(folder)}", _folder_task)
    return {"status": "processing", "task_id": tid}


@app.post("/api/documents/youtube")
async def ingest_youtube(request: Request):
    from utils.document_loader import load_youtube_transcript
    body = await request.json()
    url = body.get("url", "")
    if "youtube.com" not in url and "youtu.be" not in url:
        return JSONResponse({"error": "Not a valid YouTube URL"}, status_code=400)

    transcript = load_youtube_transcript(url)
    if not transcript:
        return JSONResponse({"error": "Could not extract transcript"}, status_code=400)

    result = rag_engine.ingest_text(transcript, source_name=f"youtube:{url}")
    return result


@app.get("/api/documents/stats")
async def document_stats():
    return rag_engine.get_stats()


@app.get("/api/documents/list")
async def list_uploaded_documents():
    """List all files in the upload directory."""
    files = []
    upload_dir = settings.UPLOAD_DIR
    if os.path.isdir(upload_dir):
        for fname in sorted(os.listdir(upload_dir)):
            fpath = os.path.join(upload_dir, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                files.append({
                    "filename": fname,
                    "path": fpath,
                    "size": stat.st_size,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified": stat.st_mtime,
                })
    return {"files": files, "upload_dir": upload_dir}


@app.delete("/api/documents/file")
async def delete_uploaded_file(request: Request):
    """Delete a single uploaded file and remove it from the RAG index."""
    body = await request.json()
    filename = body.get("filename", "").strip()
    safe_name = os.path.basename(filename)
    if not safe_name or safe_name != filename or "/" in filename or "\\" in filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)

    fpath = os.path.join(settings.UPLOAD_DIR, safe_name)
    if not os.path.isfile(fpath):
        return JSONResponse({"error": "File not found"}, status_code=404)

    # Remove from disk
    os.remove(fpath)

    # Remove from RAG index (source key stored without uuid prefix, use partial match)
    # The source name stored is the original filename without the uuid prefix
    try:
        rag_engine._ensure_init()
        all_docs = rag_engine.collection.get(include=["metadatas"])
        to_delete = []
        for i, meta in enumerate(all_docs.get("metadatas", [])):
            if meta and meta.get("source", "").endswith(filename.split("_", 1)[-1]):
                to_delete.append(all_docs["ids"][i])
        if to_delete:
            rag_engine.collection.delete(ids=to_delete)
    except Exception as e:
        print(f"  [Upload] Error removing from RAG: {e}")

    return {"status": "ok", "deleted": filename}


@app.post("/api/documents/clear")
async def clear_documents():
    return rag_engine.clear()


@app.get("/api/documents/preview")
async def preview_document(source: str, collection: str = "documents"):
    """
    Reconstruct the full text of a document from its stored chunks.
    Returns all chunks sorted by chunk_index, along with metadata.
    """
    from urllib.parse import unquote
    source = unquote(source)

    # Pick the right collection
    if collection and collection != "documents":
        engine = rag_registry.get_or_create(collection)
    else:
        engine = rag_engine

    try:
        engine._ensure_init()
        results = engine.collection.get(
            where={"source": source},
            include=["documents", "metadatas"],
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    if not results or not results.get("documents"):
        return JSONResponse({"error": f"No content found for source: {source}"}, status_code=404)

    docs = results["documents"]
    metas = results.get("metadatas") or [{}] * len(docs)

    # Sort chunks by chunk_index
    pairs = sorted(zip(docs, metas), key=lambda p: p[1].get("chunk_index", 0))
    chunks = [{"text": p[0], "index": p[1].get("chunk_index", i), "total": p[1].get("total_chunks", len(pairs))} for i, p in enumerate(pairs)]
    full_text = "\n\n".join(c["text"] for c in chunks)

    return {
        "source": source,
        "full_text": full_text,
        "chunks": chunks,
        "chunk_count": len(chunks),
    }


# ── API: Folder Watcher ────────────────────────────────

@app.get("/api/watcher/status")
async def watcher_status():
    return folder_watcher.get_status()


@app.get("/api/watcher/indexes")
async def watcher_indexes():
    """Return all per-folder knowledge indexes with their stats."""
    status = folder_watcher.get_status()
    global_stats = rag_engine.get_stats()
    indexes = [
        {
            "id": "documents",
            "label": "Uploaded Documents",
            "path": None,
            "chunk_count": global_stats["total_chunks"],
            "is_global": True,
        }
    ]
    for folder in status.get("folders", []):
        indexes.append({
            "id": folder["collection_name"],
            "label": folder["label"],
            "path": folder["path"],
            "chunk_count": folder["chunk_count"],
            "is_global": False,
        })
    return {"indexes": indexes}


@app.post("/api/watcher/add")
async def watcher_add(request: Request):
    body = await request.json()
    folder = body.get("folder", "")
    label = body.get("label", "").strip() or None
    if not folder:
        return JSONResponse({"error": "No folder specified"}, status_code=400)
        
    def _add_watch_task(progress_callback=None):
        return folder_watcher.add_folder(folder, label=label, progress_callback=progress_callback)
        
    from utils.task_manager import task_manager
    tid = task_manager.start_task(f"Add Watch Folder {os.path.basename(folder)}", _add_watch_task)
    return {"status": "processing", "task_id": tid}


@app.post("/api/watcher/remove")
async def watcher_remove(request: Request):
    body = await request.json()
    folder = body.get("folder", "")
    return folder_watcher.remove_folder(folder)


@app.post("/api/watcher/scan")
async def watcher_scan_now():
    def _scan_task(progress_callback=None):
        return folder_watcher.scan_and_index(progress_callback=progress_callback)
        
    from utils.task_manager import task_manager
    tid = task_manager.start_task("Scan Watch Folders", _scan_task)
    return {"status": "processing", "task_id": tid}

@app.post("/api/watcher/reindex")
async def watcher_reindex_all():
    """Force re-index ALL files in all watched folders, ignoring cached hashes."""
    # Clear all tracked hashes so every file is treated as new
    folder_watcher._file_hashes = {}
    folder_watcher._stats["auto_indexed"] = 0
    folder_watcher._save_state()
    
    def _reindex_task(progress_callback=None):
        return folder_watcher.scan_and_index(progress_callback=progress_callback)
        
    from utils.task_manager import task_manager
    tid = task_manager.start_task("Re-index All Folders", _reindex_task)
    return {"status": "processing", "task_id": tid}

@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    from utils.task_manager import task_manager
    task = task_manager.get_task(task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return task


# ── API: Ollama Server ─────────────────────────────────────────

@app.get("/api/ollama/status")
async def ollama_status():
    """Get current Ollama server status, models, and URL."""
    is_connected = await ollama_client.check_health()
    models = []
    if is_connected:
        models = await ollama_client.list_models()
    return {
        "connected": is_connected,
        "url": ollama_client.base_url,
        "models": models,
    }


@app.post("/api/ollama/url")
async def set_ollama_url(request: Request):
    """Update the Ollama server URL at runtime."""
    body = await request.json()
    url = body.get("url", "").strip()
    if not url or not url.startswith("http"):
        return JSONResponse({"error": "Invalid URL. Must start with http:// or https://"}, status_code=400)

    # Test connectivity
    old_url = ollama_client.base_url
    ollama_client.base_url = url
    is_connected = await ollama_client.check_health()
    if not is_connected:
        ollama_client.base_url = old_url  # revert
        return JSONResponse({"error": f"Cannot connect to Ollama at {url}. Reverted to {old_url}"}, status_code=400)

    # Persist to app_settings.json
    app_cfg = load_app_settings()
    app_cfg["ollama_url"] = url
    save_app_settings(app_cfg)

    models = await ollama_client.list_models()
    return {"status": "ok", "url": url, "models": models}


# ── API: Users ────────────────────────────────────────

@app.get("/api/users")
async def list_users():
    return {"users": chat_history.list_users()}


@app.get("/api/setup/status")
async def get_setup_status():
    users = chat_history.list_users()
    has_admin = any(u.get("is_admin") for u in users)
    return {"has_admin": has_admin}

@app.post("/api/users")
async def create_user(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    color = body.get("avatar_color", "#6366f1")
    password = body.get("password", "")
    if not name:
        return JSONResponse({"error": "Name required"}, status_code=400)
    
    users = chat_history.list_users()
    has_admin = any(u.get("is_admin") for u in users)
    
    # During first-time setup (no admin yet), allow unauthenticated creation
    if has_admin:
        requester_id = request.headers.get("X-User-Id")
        if not requester_id:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        requester = chat_history.get_user(requester_id)
        if not requester or requester.get("is_admin", 0) != 1:
            return JSONResponse({"error": "Forbidden: only admins can create new accounts"}, status_code=403)
    
    user_id = uuid.uuid4().hex[:8]
    is_admin = 1 if not has_admin else 0
    
    chat_history.create_user(user_id, name, color, is_admin=is_admin)
    
    if password:
        salt = os.urandom(16)
        pwd_hash = "pbkdf2$" + salt.hex() + "$" + hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000).hex()
        chat_history.update_user(user_id, password_hash=pwd_hash)
        
    return {"status": "ok", "id": user_id, "name": name, "avatar_color": color, "is_admin": is_admin}


@app.patch("/api/users/{user_id}")
async def update_user(user_id: str, request: Request):
    requester_id = request.headers.get("X-User-Id")
    if not requester_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    requester = chat_history.get_user(requester_id)
    is_admin = requester.get("is_admin", 0) == 1 if requester else False
    
    if requester_id != user_id and not is_admin:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
        
    body = await request.json()
    password = body.get("password")
    
    pwd_hash = None
    if password is not None:
        if password:
            salt = os.urandom(16)
            pwd_hash = "pbkdf2$" + salt.hex() + "$" + hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000).hex()
        else:
            pwd_hash = ""
            
    result = chat_history.update_user(
        user_id,
        name=body.get("name"),
        avatar_color=body.get("avatar_color"),
        password_hash=pwd_hash
    )
    if not result:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {"status": "ok", **result}

@app.post("/api/users/auth")
async def auth_user(request: Request):
    body = await request.json()
    user_id = body.get("user_id", "")
    password = body.get("password", "")
    
    with chat_history._conn() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return JSONResponse({"error": "User not found"}, status_code=404)
            
        stored_hash = dict(row).get("password_hash", "")
        if not stored_hash: # no password set
            return {"status": "ok", "authenticated": True}
            
        if stored_hash.startswith("pbkdf2$"):
            # New format verification
            parts = stored_hash.split("$")
            if len(parts) == 3:
                salt = bytes.fromhex(parts[1])
                test_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000).hex()
                if test_hash == parts[2]:
                    return {"status": "ok", "authenticated": True}
        elif stored_hash.startswith("scrypt$"):
            # Legacy scrypt fallback (if they ever had it working on py3.6+)
            try:
                parts = stored_hash.split("$")
                if len(parts) == 3:
                    salt = bytes.fromhex(parts[1])
                    test_hash = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
                    if test_hash == parts[2]:
                        return {"status": "ok", "authenticated": True}
            except AttributeError:
                pass
        else:
            # Legacy SHA-256 verification
            test_hash = hashlib.sha256(password.encode()).hexdigest()
            if test_hash == stored_hash:
                return {"status": "ok", "authenticated": True}
            
        return JSONResponse({"error": "Invalid password"}, status_code=401)

@app.post("/api/users/{user_id}/avatar")
async def upload_avatar(user_id: str, file: UploadFile = File(...)):
    user = chat_history.get_user(user_id)
    if not user:
        return JSONResponse({"error": "User not found"}, status_code=404)
        
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        return JSONResponse({"error": "Image too large. Max 5MB"}, status_code=400)
        
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
        return JSONResponse({"error": "Invalid image format"}, status_code=400)
        
    os.makedirs("data/avatars", exist_ok=True)
    avatar_path = f"/files/avatars/{user_id}{ext}"
    disk_path = f"data/generated/avatars/{user_id}{ext}"
    os.makedirs(os.path.dirname(disk_path), exist_ok=True)
    
    with open(disk_path, "wb") as f:
        f.write(content)
        
    chat_history.update_user(user_id, avatar_path=avatar_path)
    return {"status": "ok", "avatar_path": avatar_path}


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: str, request: Request):
    requester_id = request.headers.get("X-User-Id")
    if not requester_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    requester = chat_history.get_user(requester_id)
    if not requester or requester.get("is_admin", 0) != 1:
        return JSONResponse({"error": "Forbidden: Admins only"}, status_code=403)
        
    if user_id == DEFAULT_USER_ID:
        return JSONResponse({"error": "Cannot delete default user"}, status_code=400)
    chat_history.delete_user(user_id)
    return {"status": "ok"}


# ── API: App Settings ─────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    return load_app_settings()


@app.post("/api/settings")
async def update_settings(request: Request):
    body = await request.json()
    current = load_app_settings()
    current.update(body)
    save_app_settings(current)
    return {"status": "ok", **current}


@app.post("/api/factory_reset")
async def factory_reset():
    """Wipes the database and clears RAG/Uploads to reset the app."""
    try:
        chat_history.factory_reset()
        rag_engine.clear()
        
        import shutil
        if os.path.exists(settings.UPLOAD_DIR):
            shutil.rmtree(settings.UPLOAD_DIR)
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            
        settings_path = os.path.join(settings.CHROMA_PERSIST_DIR, "app_settings.json")
        if os.path.exists(settings_path):
            os.remove(settings_path)
            
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── API: Chat History ─────────────────────────────────

@app.get("/api/conversations")
async def list_conversations(folder: str = None, tag: str = None, user_id: str = DEFAULT_USER_ID):
    convs = chat_history.list_conversations(limit=50, folder=folder, tag=tag, user_id=user_id)
    return {"conversations": convs}


@app.post("/api/conversations/create-locked")
async def create_locked_conversation(request: Request):
    """Create a new conversation that is locked with a pre-hashed password."""
    body = await request.json()
    conv_id = body.get("conv_id", "").strip()
    password = body.get("password_hash", "").strip() # the client sends paintext 'password' here in standard flow, wait actually let's rehash on server
    user_id = body.get("user_id", DEFAULT_USER_ID)

    if not conv_id:
        return JSONResponse({"error": "conv_id required"}, status_code=400)
    if not password:
        return JSONResponse({"error": "password required"}, status_code=400)
    
    salt = os.urandom(16)
    password_hash = "scrypt$" + salt.hex() + "$" + hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()

    result = chat_history.create_conversation(
        conv_id=conv_id,
        title="Locked Chat",
        model=settings.DEFAULT_MODEL,
        user_id=user_id,
        is_locked=True,
        lock_password_hash=password_hash,
    )
    return {"status": "ok", "conversation": result}


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    conv = chat_history.get_conversation(conv_id)
    if not conv:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return conv


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    chat_history.delete_conversation(conv_id)
    return {"status": "ok"}


@app.post("/api/messages/{msg_id}/switch-branch")
async def switch_branch(msg_id: int, request: Request):
    """Update active_child_index on a parent message to switch branches."""
    body = await request.json()
    direction = body.get("direction", "next")
    msg = chat_history.get_message(msg_id)
    if not msg:
        return JSONResponse({"error": "Message not found"}, status_code=404)
    children = msg["children_ids"]
    idx = msg["active_child_index"]

    if direction == "_set":
        # Direct set — used when creating a new branch
        idx = max(0, min(int(body.get("index", idx)), len(children) - 1))
    elif direction == "next":
        idx = min(idx + 1, len(children) - 1)
    else:
        idx = max(idx - 1, 0)

    chat_history.set_active_child(msg_id, idx)
    return {"status": "ok", "active_child_index": idx, "children_ids": children}


@app.post("/api/conversations/{conv_id}/lock")
async def lock_conversation(conv_id: str, request: Request):
    """Lock a conversation with a password (stored as SHA-256 hash)."""
    import hashlib
    body = await request.json()
    password = body.get("password", "").strip()
    if not password:
        return JSONResponse({"error": "Password required"}, status_code=400)
    
    salt = os.urandom(16)
    pwd_hash = "scrypt$" + salt.hex() + "$" + hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
    chat_history.lock_conversation(conv_id, pwd_hash)
    return {"status": "ok", "locked": True}


@app.post("/api/conversations/{conv_id}/verify-lock")
async def verify_lock(conv_id: str, request: Request):
    """Verify password for a locked conversation. Returns ok if correct."""
    import hashlib
    body = await request.json()
    password = body.get("password", "").strip()
    if not password:
        return JSONResponse({"error": "Password required"}, status_code=400)
    
    # We retrieve the actual hash to verify instead of delegating a raw query to chat_history
    conv = chat_history.get_conversation(conv_id)
    if not conv:
        return JSONResponse({"error": "Conversation not found"}, status_code=404)
        
    stored_hash = conv.get("lock_password_hash", "")
    ok = False
    if stored_hash.startswith("scrypt$"):
        parts = stored_hash.split("$")
        if len(parts) == 3:
            salt = bytes.fromhex(parts[1])
            test_hash = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
            ok = (test_hash == parts[2])
    else:
        # Legacy sha256
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        ok = (pwd_hash == stored_hash)

    if ok:
        return {"status": "ok", "verified": True}
    return JSONResponse({"error": "Incorrect password"}, status_code=403)


@app.post("/api/conversations/{conv_id}/unlock")
async def unlock_conversation(conv_id: str, request: Request):
    """Permanently remove the lock from a conversation (requires password verification)."""
    import hashlib
    body = await request.json()
    password = body.get("password", "").strip()
    if password:
        conv = chat_history.get_conversation(conv_id)
        stored_hash = conv.get("lock_password_hash", "") if conv else ""
        ok = False
        if stored_hash.startswith("scrypt$"):
            parts = stored_hash.split("$")
            if len(parts) == 3:
                salt = bytes.fromhex(parts[1])
                test_hash = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
                ok = (test_hash == parts[2])
        else:
            pwd_hash = hashlib.sha256(password.encode()).hexdigest()
            ok = (pwd_hash == stored_hash)
            
        if not ok:
            return JSONResponse({"error": "Incorrect password"}, status_code=403)
    chat_history.unlock_conversation(conv_id)
    return {"status": "ok", "locked": False}



@app.patch("/api/conversations/{conv_id}")
async def rename_conversation(conv_id: str, request: Request):
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        return JSONResponse({"error": "Empty title"}, status_code=400)
    chat_history.update_title(conv_id, title)
    return {"status": "ok", "title": title}


@app.get("/api/conversations/{conv_id}/export")
async def export_conversation(conv_id: str, format: str = "md"):
    if format == "md":
        md = chat_history.export_markdown(conv_id)
        if not md:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return JSONResponse({"markdown": md, "conversation_id": conv_id})
    elif format == "pdf":
        md = chat_history.export_markdown(conv_id)
        if not md:
            return JSONResponse({"error": "Not found"}, status_code=404)
        conv = chat_history.get_conversation(conv_id)
        result = generate_pdf(conv["title"], md)
        if result.get("status") == "ok":
            return FileResponse(result["path"], filename=result["filename"], media_type="application/pdf")
        return JSONResponse(result, status_code=500)
    return JSONResponse({"error": "Unsupported format. Use 'md' or 'pdf'"}, status_code=400)


# ── API: Search ───────────────────────────────────────

@app.get("/api/conversations/search/{query}")
async def search_conversations(query: str, user_id: str = DEFAULT_USER_ID):
    results = chat_history.search(query, user_id=user_id)
    return {"results": results, "query": query}


# ── API: AI Memory ────────────────────────────────────

@app.get("/api/memory")
async def get_memory(user_id: str = DEFAULT_USER_ID):
    return {"memory": chat_history.get_all_memory(user_id)}


@app.post("/api/memory")
async def save_memory(request: Request):
    body = await request.json()
    key = body.get("key", "").strip()
    value = body.get("value", "").strip()
    user_id = body.get("user_id", DEFAULT_USER_ID)
    if not key or not value:
        return JSONResponse({"error": "Key and value required"}, status_code=400)
    result = chat_history.save_memory(key, value, user_id)
    return {"status": "ok", **result}


@app.delete("/api/memory/{key}")
async def delete_memory(key: str, user_id: str = DEFAULT_USER_ID):
    chat_history.delete_memory(key, user_id)
    return {"status": "ok"}


# ── API: Document Digest ──────────────────────────────

@app.post("/api/documents/digest")
async def digest_documents(request: Request):
    body = await request.json()
    model = body.get("model", None)

    stats = rag_engine.get_stats()
    if stats.get("total_chunks", 0) == 0:
        return JSONResponse({"error": "No documents indexed yet. Upload some files first."}, status_code=400)

    digest_query = "Provide a comprehensive digest of all the documents. For each document or major topic, write a clear summary of its key points, main ideas, and important facts. Format the output with headings for each document/topic."
    context = rag_engine.build_context(digest_query)

    memory_block = chat_history.build_memory_prompt(DEFAULT_USER_ID)
    sys_prompt = "You are a document analysis assistant. Create a well-structured digest of the provided documents."
    if memory_block:
        sys_prompt += "\n\n" + memory_block

    async def generate():
        async for token in local_llm.stream_chat(
            message=digest_query,
            model=model,
            context=context,
            history=[],
            system_prompt=sys_prompt,
        ):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── API: Multi-Model Compare ──────────────────────────

@app.post("/api/chat/compare")
async def chat_compare(request: Request):
    """Stream responses from two models simultaneously, labeled by index."""
    import asyncio

    body = await request.json()
    message = body.get("message", "")
    models = body.get("models", [])
    history = body.get("history", [])
    mode = body.get("mode", "plain")
    session_system_prompt = body.get("session_system_prompt", None)

    if not message.strip():
        return JSONResponse({"error": "Empty message"}, status_code=400)
    if len(models) < 2:
        return JSONResponse({"error": "Provide at least 2 models"}, status_code=400)

    context = ""
    if mode == "docs":
        context = rag_engine.build_context(message)

    if session_system_prompt and session_system_prompt.strip():
        system_prompt = session_system_prompt.strip()
    else:
        system_prompt = None
        persona = chat_history.get_persona("default")
        if persona and persona.get("prompt"):
            system_prompt = persona["prompt"]
        if not system_prompt:
            system_prompt = SYSTEM_PROMPT
    memory_block = chat_history.build_memory_prompt(DEFAULT_USER_ID)
    if memory_block:
        system_prompt = memory_block + "\n\n" + (system_prompt or "")

    async def stream_model(model_name: str, idx: int, queue: asyncio.Queue):
        async for token in local_llm.stream_chat(
            message=message, model=model_name, context=context,
            history=history, system_prompt=system_prompt,
        ):
            await queue.put(json.dumps({"model_idx": idx, "model": model_name, "token": token}))
        await queue.put(json.dumps({"model_idx": idx, "model": model_name, "done": True}))

    async def generate():
        queue: asyncio.Queue = asyncio.Queue()
        tasks = [
            asyncio.create_task(stream_model(m, i, queue))
            for i, m in enumerate(models[:2])
        ]
        done_count = 0
        while done_count < len(tasks):
            item = await queue.get()
            data = json.loads(item)
            yield f"data: {item}\n\n"
            if data.get("done"):
                done_count += 1
        for t in tasks:
            t.cancel()

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── API: Conversation Metadata ────────────────────────

@app.patch("/api/conversations/{conv_id}/meta")
async def update_conversation_meta(conv_id: str, request: Request):
    """Update folder, tags, or persona for a conversation."""
    body = await request.json()
    chat_history.update_conversation(conv_id, **body)
    return {"status": "ok"}


@app.get("/api/folders")
async def list_folders(user_id: str = DEFAULT_USER_ID):
    return {"folders": chat_history.get_folders(user_id)}


@app.get("/api/tags")
async def list_tags(user_id: str = DEFAULT_USER_ID):
    return {"tags": chat_history.get_all_tags(user_id)}


# ── API: Personas ─────────────────────────────────────

@app.get("/api/personas")
async def api_list_personas():
    return {"personas": chat_history.list_personas()}


@app.get("/api/personas/{persona_id}")
async def api_get_persona(persona_id: str):
    p = chat_history.get_persona(persona_id)
    if not p:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return p


@app.post("/api/personas")
async def api_save_persona(request: Request):
    body = await request.json()
    pid = body.get("id", uuid.uuid4().hex[:8])
    name = body.get("name", "").strip() or "Default"
    prompt = body.get("prompt", "").strip()
    if not name:
        return JSONResponse({"error": "Name required"}, status_code=400)
    # Blank prompt is OK — means "use app default system prompt"
    result = chat_history.save_persona(pid, name, prompt)
    return {"status": "ok", **result}


@app.delete("/api/personas/{persona_id}")
async def api_delete_persona(persona_id: str):
    chat_history.delete_persona(persona_id)
    return {"status": "ok"}


# ── API: Document Generation ──────────────────────────

@app.post("/api/generate/docx")
async def gen_docx(request: Request):
    body = await request.json()
    result = generate_docx(body.get("title", "Document"), body.get("content", ""))
    if result.get("status") == "ok":
        result["url"] = f"/files/{result['filename']}"
    return result


@app.post("/api/generate/pdf")
async def gen_pdf(request: Request):
    body = await request.json()
    result = generate_pdf(body.get("title", "Document"), body.get("content", ""))
    if result.get("status") == "ok":
        result["url"] = f"/files/{result['filename']}"
    return result


@app.post("/api/generate/xlsx")
async def gen_xlsx(request: Request):
    body = await request.json()
    result = generate_xlsx(body.get("title", "Spreadsheet"), body.get("content", ""))
    if result.get("status") == "ok":
        result["url"] = f"/files/{result['filename']}"
    return result


# ── API: Image Upload (for vision models) ─────────────

@app.post("/api/upload/image")
async def upload_image(file: UploadFile = File(...)):
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return JSONResponse({"error": f"Unsupported image type: {ext}"}, status_code=400)

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        return JSONResponse({"error": "Image too large. Max 10MB"}, status_code=400)

    b64 = base64.b64encode(content).decode("utf-8")
    return {"status": "ok", "base64": b64, "filename": file.filename, "size": len(content)}


# ── API: Voice Input ──────────────────────────────────

@app.post("/api/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)):
    from utils.voice_input import transcribe_audio
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        return JSONResponse({"error": "Audio too large. Max 25MB"}, status_code=400)

    result = transcribe_audio(content, file.filename)
    return result


@app.get("/api/voice/status")
async def voice_status():
    from utils.voice_input import is_available as whisper_available
    return {"available": whisper_available()}


# ── API: Templates ────────────────────────────────────

@app.post("/api/templates/upload")
async def upload_template(file: UploadFile = File(...)):
    """Upload a form/template document for reuse."""
    from utils.template_engine import save_template
    ext = os.path.splitext(file.filename)[1].lower()
    allowed = {".txt", ".pdf", ".docx", ".md"}
    if ext not in allowed:
        return JSONResponse(
            {"error": f"Unsupported template type: {ext}. Use: {', '.join(allowed)}"},
            status_code=400,
        )

    # Save to temp then register as template
    tmp_path = os.path.join(settings.UPLOAD_DIR, f"tmp_{uuid.uuid4().hex}_{file.filename}")
    content = await file.read()
    with open(tmp_path, "wb") as f:
        f.write(content)

    result = save_template(tmp_path, file.filename)
    os.remove(tmp_path)

    return {
        "status": "ok",
        "template_id": result["id"],
        "name": result["name"],
        "fields": len(result.get("structure", {}).get("fields", [])),
        "structure": result.get("structure", {}),
    }


@app.get("/api/templates")
async def api_list_templates():
    from utils.template_engine import list_templates
    return {"templates": list_templates()}


@app.get("/api/templates/{template_id}")
async def api_get_template(template_id: str):
    from utils.template_engine import get_template
    t = get_template(template_id)
    if not t:
        return JSONResponse({"error": "Template not found"}, status_code=404)
    return t


@app.delete("/api/templates/{template_id}")
async def api_delete_template(template_id: str):
    from utils.template_engine import delete_template
    delete_template(template_id)
    return {"status": "ok"}

@app.post("/api/templates/{template_id}/fill")
async def fill_template_endpoint(template_id: str, request: Request):
    """Fill a template.

    Mode A (Smart Fill — content file upload):
        multipart/form-data with fields: content_file (UploadFile), model (str)
        → runs the full JSON-extraction pipeline through template_engine.run_fill_pipeline()

    Mode B (AI Fill — free text instructions, legacy):
        application/json with fields: instructions (str), model (str), output_format (str)
        → calls the existing build_fill_prompt / generate_from_template path
    """
    import tempfile
    from utils.template_engine import run_fill_pipeline
    from utils.extractor import extract_text as _extract

    ct = request.headers.get("content-type", "")

    # ── Mode A: multipart (content file upload) ────────────────────────────
    if "multipart" in ct:
        form = await request.form()
        content_file_obj = form.get("content_file")
        model = form.get("model", None) or None

        if not content_file_obj:
            return JSONResponse({"error": "content_file is required"}, status_code=400)

        template = get_template(template_id)
        if not template:
            return JSONResponse({"error": "Template not found"}, status_code=404)

        content_bytes = await content_file_obj.read()
        c_ext = os.path.splitext(content_file_obj.filename)[1].lower() or ".txt"
        with tempfile.NamedTemporaryFile(suffix=c_ext, delete=False) as tmp:
            tmp.write(content_bytes)
            c_path = tmp.name
        try:
            content_text = _extract(c_path)
        finally:
            os.unlink(c_path)

        result = await run_fill_pipeline(
            template_id=template_id,
            content_text=content_text,
            model=model,
        )
        return result

    # ── Mode B: JSON (AI Fill — instruction-based, legacy) ─────────────────
    from utils.template_engine import get_template, build_fill_prompt, generate_from_template
    body = await request.json()
    instructions = body.get("instructions", "")
    model = body.get("model", None)
    output_format = body.get("output_format", None)

    if not instructions.strip():
        return JSONResponse({"error": "No instructions provided"}, status_code=400)

    template = get_template(template_id)
    if not template:
        return JSONResponse({"error": "Template not found"}, status_code=404)

    fill_prompt = build_fill_prompt(template, instructions)
    full_response = ""
    async for token in local_llm.stream_chat(
        message=fill_prompt, model=model, context="", history=[],
    ):
        full_response += token

    result = generate_from_template(template_id, full_response, output_format)
    if result.get("status") == "ok":
        result["url"] = f"/files/{result['filename']}"
    return result


@app.post("/api/form-fill")
async def smart_form_fill_v2(
    template_file: UploadFile = File(None),
    content_file: UploadFile = File(...),
    template_id: str = Form(default=""),
    model: str = Form(default=""),
    output_format: str = Form(default="docx"),
):
    """
    Smart Fill v2: upload two files → LLM returns JSON map → python-docx fills template.
    The template is saved automatically if template_file is provided.
    If template_id is provided (previously saved), template_file is optional.
    """
    import tempfile
    from utils.template_engine import run_fill_pipeline, save_template
    from utils.extractor import extract_text as _extract

    # ── Resolve template_id ────────────────────────────────────────────────
    if template_file:
        ext = os.path.splitext(template_file.filename)[1].lower()
        if ext not in {".docx", ".pdf", ".txt", ".md"}:
            return JSONResponse({"error": f"Unsupported template type: {ext}"}, status_code=400)
        tpl_bytes = await template_file.read()
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(tpl_bytes)
            tpl_tmp = tmp.name
        try:
            saved = save_template(tpl_tmp, template_file.filename)
            tid = saved["id"]
        finally:
            os.unlink(tpl_tmp)
    elif template_id:
        tid = template_id
    else:
        return JSONResponse({"error": "Provide template_file or template_id"}, status_code=400)

    # ── Extract content text ───────────────────────────────────────────────
    c_ext = os.path.splitext(content_file.filename)[1].lower() or ".txt"
    c_bytes = await content_file.read()
    with tempfile.NamedTemporaryFile(suffix=c_ext, delete=False) as tmp:
        tmp.write(c_bytes)
        c_path = tmp.name
    try:
        content_text = _extract(c_path)
    finally:
        os.unlink(c_path)

    # ── Run pipeline ───────────────────────────────────────────────────────
    result = await run_fill_pipeline(
        template_id=tid,
        content_text=content_text,
        model=model or None,
    )
    return result


if __name__ == "__main__":
    import uvicorn
    print(f"\n  🚀 {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"  → http://localhost:{settings.PORT}")
    print(f"  → Models: {os.path.abspath(settings.MODELS_DIR)}")
    print(f"  → Profile: {PROFILE}\n")
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)

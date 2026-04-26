"""
OpenChat Local — Local LLM Engine
Dual-backend: Runs GGUF models via llama-cpp-python AND HuggingFace SafeTensors models
via transformers, both with Apple Metal GPU acceleration.
"""
import os
import shutil
import asyncio
import glob
import json
import threading
from pathlib import Path
from typing import AsyncGenerator, List, Dict, Optional
from functools import partial

from config import settings


SYSTEM_PROMPT = """You are a helpful, harmless, and honest AI assistant. Your goal is to be genuinely useful while being thoughtful about safety and accuracy.

## Core Behavior

- Be warm, direct, and conversational. Avoid over-formatting with bullet points, headers, and bold text unless the user asks for it or the content genuinely requires structure.
- Write in natural prose and paragraphs for most responses. Keep casual conversations short — a few sentences is often enough.
- Don't start responses with "Great question!" or similar filler. Just answer.
- Don't use emojis unless the user does.
- Avoid words like "genuinely," "honestly," "straightforward," and "delve."
- Don't ask more than one clarifying question per response. When a request is slightly ambiguous, make a reasonable assumption, proceed, and note the assumption briefly.

## Language Matching

- ALWAYS respond in the same language the user writes in. If the user writes in Vietnamese, respond in Vietnamese. If they write in French, respond in French. This applies to every message — detect the language of each new message and match it.
- If the user switches languages mid-conversation, switch with them immediately.
- If the user writes in a mix of languages (e.g., code-switching between English and another language), match their dominant language while preserving any technical terms or proper nouns they used in the other language.
- Never default to English unless the user is writing in English.
- Maintain the same tone, quality, and depth of response regardless of which language you're using. Don't give shorter or less helpful answers just because the language isn't English.

## Knowledge & Accuracy

- If you're unsure about something, say so. Don't fabricate facts, citations, or quotes.
- Distinguish clearly between what you know confidently and what you're uncertain about.
- For time-sensitive topics (current events, who holds a position, recent releases), acknowledge that your training data has a cutoff and you may not have the latest information.

## Tone & Style

- Match the user's energy. If they're casual, be casual. If they're formal, be more precise.
- Illustrate explanations with examples, analogies, or thought experiments when helpful.
- Be willing to express nuanced views on complex topics rather than giving empty "both sides" answers, but present alternative perspectives fairly.
- Push back constructively when the user is mistaken — don't just agree to be agreeable — but do so with kindness.

## Safety & Ethics

- Don't help with creating weapons, malware, or harmful substances.
- Don't generate sexual content involving minors.
- Don't write persuasive content that puts fabricated quotes in real people's mouths.
- For legal or financial questions, share relevant information but remind the user you're not a professional advisor.
- Care about the user's wellbeing. Don't encourage self-destructive behavior even if asked.

## Formatting Defaults

- Default to prose. Use lists only when the content is inherently list-like or the user requests it.
- For code, use fenced code blocks with the language specified.
- Keep responses as concise as the question warrants. A simple question deserves a simple answer."""


def _check_hf_available() -> bool:
    """Check if transformers + torch are importable."""
    try:
        import torch
        import transformers
        return True
    except ImportError:
        return False


class LocalLLM:
    """Manages GGUF and SafeTensors model loading, inference, and model directory operations."""

    def __init__(self):
        self.models_dir: str = settings.MODELS_DIR
        os.makedirs(self.models_dir, exist_ok=True)

        self._llm = None              # Llama instance OR HF model
        self._tokenizer = None        # HF tokenizer (None for GGUF)
        self._backend = None          # "gguf" or "hf"
        self._loaded_model: str = ""  # display name of loaded model
        self._loaded_path: str = ""   # full path of loaded model
        self._lock = asyncio.Lock()   # serialise load/unload
        self._is_streaming: bool = False  # guard: block unload during active stream

    # ── Health ────────────────────────────────────────────────────────────

    async def check_health(self) -> bool:
        """Returns True if at least one model is available."""
        models = self.scan_models()
        return len(models) > 0

    def get_all_model_dirs(self) -> List[str]:
        """Return the default models_dir and any configured extra directories."""
        dirs = [self.models_dir]
        extra = settings.EXTRA_MODELS_DIRS.strip()
        if extra:
            for d in extra.split(","):
                d = d.strip()
                if d and os.path.isdir(d):
                    dirs.append(d)
        # return unique directories preserving order
        return list(dict.fromkeys(dirs))

    # ── Model Scanning ────────────────────────────────────────────────────

    def scan_models(self) -> List[Dict]:
        """Scan all model directories for GGUF files and SafeTensors directories."""
        results = []

        for model_dir in self.get_all_model_dirs():
            # ── GGUF files ──
            for path in sorted(glob.glob(os.path.join(model_dir, "**", "*.gguf"), recursive=True)):
                stat = os.stat(path)
                name = os.path.basename(path)
                # prevent duplicates if same filename exists in multiple dirs
                if not any(r["name"] == name for r in results):
                    results.append({
                        "name": name,
                        "path": path,
                        "size": stat.st_size,
                        "size_gb": round(stat.st_size / (1024 ** 3), 2),
                        "modified": stat.st_mtime,
                        "loaded": (path == self._loaded_path),
                        "format": "gguf",
                    })

            # ── SafeTensors directories ──
            # A valid HF model dir contains config.json
            for entry in sorted(Path(model_dir).iterdir()):
                if not entry.is_dir():
                    continue
                config_path = entry / "config.json"
                if not config_path.exists():
                    continue
                # Check for .safetensors or .bin files at ANY depth (handles sharded models)
                has_weights = (
                    any(entry.rglob("*.safetensors"))
                    or any(entry.rglob("*.bin"))
                )
                if not has_weights:
                    continue

                # Calculate total size
                total_size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                mod_time = config_path.stat().st_mtime
                dir_path = str(entry)
                dir_name = entry.name

                if not any(r["name"] == dir_name for r in results):
                    results.append({
                        "name": dir_name,
                        "path": dir_path,
                        "size": total_size,
                        "size_gb": round(total_size / (1024 ** 3), 2),
                        "modified": mod_time,
                        "loaded": (dir_path == self._loaded_path),
                        "format": "safetensors",
                    })

        return results

    async def list_models(self) -> List[Dict]:
        """Return local GGUF/HF models + Ollama models (if Ollama is reachable)."""
        local = self.scan_models()
        hf_ok = _check_hf_available()
        result = [
            {
                "name": m["name"],
                "size": m["size"],
                "size_gb": m["size_gb"],
                "modified": m["modified"],
                "loaded": m["loaded"],
                "format": m["format"],
                "family": "",
                "parameter_size": "",
                "quantization": _guess_quant(m["name"]) if m["format"] == "gguf" else "fp16",
                "available": True if m["format"] == "gguf" else hf_ok,
                "provider": "local",
            }
            for m in local
        ]

        # Append Ollama models when Ollama is running
        try:
            from utils.ollama_client import ollama_client
            if await ollama_client.check_health():
                ollama_models = await ollama_client.list_models()
                for om in ollama_models:
                    result.append({
                        "name": om["name"],
                        "size": om.get("size", 0),
                        "size_gb": round(om.get("size", 0) / (1024 ** 3), 2),
                        "modified": om.get("modified", ""),
                        "loaded": False,
                        "format": "ollama",
                        "family": om.get("family", ""),
                        "parameter_size": om.get("parameter_size", ""),
                        "quantization": om.get("quantization", ""),
                        "available": True,
                        "provider": "ollama",
                    })
        except Exception as e:
            print(f"  [LLM] Could not fetch Ollama models: {e}")

        return result

    # ── Model Loading ─────────────────────────────────────────────────────

    def _resolve_model_path(self, model_name: Optional[str]) -> str:
        """Convert a model name to a full path, or pick a default."""
        if not model_name:
            model_name = settings.DEFAULT_MODEL

        # Already a full path?
        if model_name and os.path.isfile(model_name):
            return model_name
        if model_name and os.path.isdir(model_name):
            config = os.path.join(model_name, "config.json")
            if os.path.isfile(config):
                return model_name

        # Exact match in any models dir (file or directory)
        for model_dir in self.get_all_model_dirs():
            candidate = os.path.join(model_dir, model_name) if model_name else ""
            if candidate and os.path.isfile(candidate):
                return candidate
            if candidate and os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "config.json")):
                return candidate

            # Append .gguf if missing
            if model_name and not model_name.endswith(".gguf"):
                candidate_gguf = candidate + ".gguf"
                if os.path.isfile(candidate_gguf):
                    return candidate_gguf

        # Partial / substring match
        for m in self.scan_models():
            if model_name and model_name.lower() in m["name"].lower():
                return m["path"]

        # Fallback: first available model
        models = self.scan_models()
        if models:
            return models[0]["path"]

        raise FileNotFoundError(f"No model found matching '{model_name}' in {self.models_dir}")

    def _detect_format(self, path: str) -> str:
        """Determine if a path is a GGUF file or a HuggingFace model directory."""
        if os.path.isfile(path) and path.endswith(".gguf"):
            return "gguf"
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "config.json")):
            return "safetensors"
        # Fallback: treat .gguf as gguf, everything else as unknown
        if path.endswith(".gguf"):
            return "gguf"
        return "unknown"

    def load_model(self, model_name: Optional[str] = None) -> Dict:
        """Load a model into memory. Auto-detects GGUF vs SafeTensors."""
        path = self._resolve_model_path(model_name)

        # Already loaded?
        if self._llm is not None and self._loaded_path == path:
            return {"status": "already_loaded", "model": self._loaded_model, "format": self._backend}

        # Unload previous
        self.unload_model()

        fmt = self._detect_format(path)

        if fmt == "gguf":
            return self._load_gguf(path)
        elif fmt == "safetensors":
            return self._load_hf(path)
        else:
            raise FileNotFoundError(f"Unsupported model format at {path}")

    def _load_gguf(self, path: str) -> Dict:
        """Load a GGUF model via llama-cpp-python."""
        from llama_cpp import Llama

        name = os.path.basename(path)
        print(f"  [LLM] Loading GGUF: {name} ({os.path.getsize(path) / 1e9:.1f} GB)…")

        self._llm = Llama(
            model_path=path,
            n_ctx=settings.DEFAULT_N_CTX,
            n_gpu_layers=settings.DEFAULT_N_GPU_LAYERS,
            verbose=False,
            chat_format="chatml",
        )

        self._backend = "gguf"
        self._tokenizer = None
        self._loaded_model = name
        self._loaded_path = path

        print(f"  [LLM] ✓ Loaded {name} (GGUF)")
        return {"status": "ok", "model": name, "format": "gguf"}

    def _load_hf(self, model_dir: str) -> Dict:
        """Load a HuggingFace SafeTensors model via transformers."""
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError:
            return {
                "status": "error",
                "error": "torch and transformers are required for SafeTensors models. "
                         "Run: pip install torch transformers accelerate"
            }

        name = os.path.basename(model_dir)
        print(f"  [LLM] Loading SafeTensors: {name}…")

        # Detect best device
        if torch.backends.mps.is_available():
            device = "mps"
            print(f"  [LLM]   Using Apple Metal (MPS) GPU")
        elif torch.cuda.is_available():
            device = "cuda"
            print(f"  [LLM]   Using CUDA GPU")
        else:
            device = "cpu"
            print(f"  [LLM]   Using CPU (no GPU detected)")

        try:
            # Use "auto" dtype to let transformers handle bfloat16/float16/float32 appropriately
            dtype = "auto"
            
            # Check for accelerate presence for smarter device mapping
            has_accelerate = False
            try:
                import accelerate
                has_accelerate = True
            except ImportError:
                pass

            self._tokenizer = AutoTokenizer.from_pretrained(
                model_dir, trust_remote_code=True
            )

            # For MPS, device_map="auto" is sometimes unstable depending on transformers version
            # We use it only for CUDA or if accelerate is explicitly preferred.
            # Otherwise load to CPU and move to MPS manually.
            use_device_map = has_accelerate and (device == "cuda")
            
            self._llm = AutoModelForCausalLM.from_pretrained(
                model_dir,
                torch_dtype=dtype,
                device_map="auto" if use_device_map else None,
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )

            # For MPS or CPU, manually move if not using device_map
            if not use_device_map and device != "cpu":
                self._llm = self._llm.to(device)

            self._llm.eval()

        except Exception as e:
            self._llm = None
            self._tokenizer = None
            error_msg = str(e)
            print(f"  [LLM] ✗ Failed to load {name}: {error_msg}")
            
            # Detailed help for common errors
            if "out of memory" in error_msg.lower():
                error_msg = "Out of VRAM/Memory. Try a smaller model or a GGUF quantized version."
            elif "config.json" in error_msg.lower():
                error_msg = "Missing config.json. Ensure the full model directory was downloaded."
            
            return {"status": "error", "error": error_msg}

        self._backend = "hf"
        self._loaded_model = name
        self._loaded_path = model_dir

        print(f"  [LLM] ✓ Loaded {name} (SafeTensors, {device})")
        return {"status": "ok", "model": name, "format": "safetensors", "device": device}

    def unload_model(self):
        """Free the loaded model from memory."""
        if self._is_streaming:
            print("  [LLM] ⚠ Cannot unload — model is currently streaming a response. Will unload after stream completes.")
            return
        if self._llm is not None:
            name = self._loaded_model
            backend = self._backend

            # For HF models, explicitly clear GPU memory
            if self._backend == "hf":
                try:
                    import torch
                    del self._llm
                    self._llm = None
                    if torch.backends.mps.is_available():
                        torch.mps.empty_cache()
                    elif torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    self._llm = None
            else:
                del self._llm
                self._llm = None

            self._tokenizer = None
            self._backend = None
            self._loaded_model = ""
            self._loaded_path = ""
            print(f"  [LLM] Unloaded {name} ({backend})")

    def _ensure_loaded(self, model_name: Optional[str] = None):
        """Make sure a model is loaded before inference. Never reloads during an active stream."""
        if self._is_streaming:
            # A stream is active — do not touch the loaded model under any circumstances.
            if self._llm is None:
                raise RuntimeError("Another stream is in progress and no model is loaded.")
            return

        if model_name:
            try:
                desired_path = self._resolve_model_path(model_name)
            except FileNotFoundError:
                desired_path = None
            # Only reload if the requested model is definitively different from the loaded one
            if desired_path and desired_path != self._loaded_path and self._llm is not None:
                print(f"  [LLM] Requested model '{model_name}' differs from loaded '{self._loaded_model}' — switching.")
                self.load_model(model_name)
                return
            elif desired_path and self._llm is None:
                self.load_model(model_name)
                return

        if self._llm is None:
            self.load_model(model_name)

    # ── Chat Streaming ────────────────────────────────────────────────────

    async def stream_chat(
        self,
        message: str,
        model: str = None,
        context: str = "",
        history: List[Dict] = None,
        images: List[str] = None,
        system_prompt: str = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat completion. Routes to Ollama or local backend."""

        # ── Detect if this is an Ollama model ──────────────────────────────
        # Ollama model names contain ":" (e.g. llama3.2:3b) or match a known Ollama model
        is_ollama = False
        if model:
            try:
                from utils.ollama_client import ollama_client
                if await ollama_client.check_health():
                    ollama_names = {m["name"] for m in await ollama_client.list_models()}
                    if model in ollama_names or ":" in model:
                        is_ollama = True
            except Exception:
                pass

        if is_ollama:
            from utils.ollama_client import ollama_client
            async for token in ollama_client.stream_chat(
                message=message,
                model=model,
                context=context,
                history=history,
                images=images,
                system_prompt=system_prompt,
            ):
                yield token
            return

        # ── Local backend (GGUF / HF) ──────────────────────────────────────
        async with self._lock:
            if self._is_streaming:
                pass
            try:
                self._ensure_loaded(model)
            except FileNotFoundError as e:
                yield f"[Error: {e}. Please download a model first.]"
                return
            except Exception as e:
                yield f"[Error loading model: {e}]"
                return

            backend = self._backend
            self._is_streaming = True

        try:
            if backend == "gguf":
                async for token in self._stream_gguf(message, context, history, images, system_prompt):
                    yield token
            elif backend == "hf":
                async for token in self._stream_hf(message, context, history, images, system_prompt):
                    yield token
            else:
                yield "[Error: No model backend loaded]"
        finally:
            self._is_streaming = False

    async def _stream_gguf(
        self, message, context, history, images, system_prompt
    ) -> AsyncGenerator[str, None]:
        """Stream from llama-cpp-python (GGUF)."""
        prompt = system_prompt or SYSTEM_PROMPT
        messages = [{"role": "system", "content": prompt}]

        if history:
            for h in history[-10:]:
                messages.append({"role": h["role"], "content": h["content"]})

        user_content_str = message
        if context:
            user_content_str = (
                f"Use the following context from the user's documents to answer the question.\n\n"
                f"--- DOCUMENT CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                f"Question: {message}"
            )

        if images:
            user_content_arr = []
            for img_b64 in images:
                img_url = img_b64 if img_b64.startswith("data:image") else f"data:image/jpeg;base64,{img_b64}"
                user_content_arr.append({"type": "image_url", "image_url": {"url": img_url}})
            user_content_arr.append({"type": "text", "text": user_content_str})
            messages.append({"role": "user", "content": user_content_arr})
        else:
            messages.append({"role": "user", "content": user_content_str})

        try:
            loop = asyncio.get_running_loop()
            stream = await loop.run_in_executor(
                None,
                partial(
                    self._llm.create_chat_completion,
                    messages=messages,
                    stream=True,
                    max_tokens=settings.DEFAULT_MAX_TOKENS,
                    temperature=0.7,
                    top_p=0.9,
                ),
            )
            for chunk in stream:
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    yield token
                    await asyncio.sleep(0)
        except Exception as e:
            yield f"[Error during inference: {e}]"

    async def _stream_hf(
        self, message, context, history, images, system_prompt
    ) -> AsyncGenerator[str, None]:
        """Stream from HuggingFace transformers model."""
        try:
            import torch
            from transformers import TextIteratorStreamer
        except ImportError:
            yield "[Error: transformers not installed]"
            return

        prompt = system_prompt or SYSTEM_PROMPT
        messages = [{"role": "system", "content": prompt}]

        if history:
            for h in history[-10:]:
                messages.append({"role": h["role"], "content": h["content"]})

        user_content_str = message
        if context:
            user_content_str = (
                f"Use the following context from the user's documents to answer the question.\n\n"
                f"--- DOCUMENT CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                f"Question: {message}"
            )

        if images:
            user_content_arr = []
            for img_b64 in images:
                img_url = img_b64 if img_b64.startswith("data:image") else f"data:image/jpeg;base64,{img_b64}"
                user_content_arr.append({"type": "image_url", "image_url": {"url": img_url}})
            user_content_arr.append({"type": "text", "text": user_content_str})
            messages.append({"role": "user", "content": user_content_arr})
        else:
            messages.append({"role": "user", "content": user_content_str})

        try:
            # Apply chat template if available
            if hasattr(self._tokenizer, "apply_chat_template"):
                input_text = self._tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
            else:
                # Fallback: simple concatenation
                parts = []
                for m in messages:
                    role = m["role"]
                    content = m["content"]
                    if role == "system":
                        parts.append(f"System: {content}")
                    elif role == "user":
                        parts.append(f"User: {content}")
                    elif role == "assistant":
                        parts.append(f"Assistant: {content}")
                parts.append("Assistant:")
                input_text = "\n\n".join(parts)

            device = self._llm.device if hasattr(self._llm, "device") else "cpu"
            inputs = self._tokenizer(input_text, return_tensors="pt").to(device)
            input_len = inputs["input_ids"].shape[1]

            # Create streamer
            streamer = TextIteratorStreamer(
                self._tokenizer,
                skip_prompt=True,
                skip_special_tokens=True,
            )

            # Generation params
            gen_kwargs = {
                **inputs,
                "max_new_tokens": settings.DEFAULT_MAX_TOKENS,
                "temperature": 0.7,
                "top_p": 0.9,
                "do_sample": True,
                "streamer": streamer,
            }

            # Run generation in background thread
            thread = threading.Thread(target=self._llm.generate, kwargs=gen_kwargs)
            thread.start()

            # Yield tokens as they arrive
            for token_text in streamer:
                if token_text:
                    yield token_text
                    await asyncio.sleep(0)

            thread.join(timeout=300)  # 5 minutes — large models can be slow on CPU

        except Exception as e:
            yield f"[Error during HF inference: {e}]"

    # ── Title Generation ──────────────────────────────────────────────────

    async def generate_title(self, message: str, model: str = None) -> str:
        """Generate a short title for a conversation."""
        async with self._lock:
            try:
                self._ensure_loaded(model)
            except Exception:
                return "New Chat"

        if self._backend == "gguf":
            return await self._generate_title_gguf(message)
        elif self._backend == "hf":
            return await self._generate_title_hf(message)
        return "New Chat"

    async def _generate_title_gguf(self, message: str) -> str:
        messages = [
            {"role": "system", "content": "Generate a very short title (3-6 words) for this conversation. Reply with ONLY the title, nothing else."},
            {"role": "user", "content": message},
        ]
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                partial(
                    self._llm.create_chat_completion,
                    messages=messages,
                    max_tokens=30,
                    temperature=0.3,
                ),
            )
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip() or "New Chat"
        except Exception:
            return "New Chat"

    async def _generate_title_hf(self, message: str) -> str:
        try:
            import torch

            prompt = f"Generate a very short title (3-6 words) for this conversation.\n\nUser: {message}\n\nTitle:"
            device = self._llm.device if hasattr(self._llm, "device") else "cpu"
            inputs = self._tokenizer(prompt, return_tensors="pt").to(device)

            with torch.no_grad():
                outputs = self._llm.generate(
                    **inputs, max_new_tokens=20, temperature=0.3, do_sample=True
                )
            text = self._tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            return text.strip().split("\n")[0][:60] or "New Chat"
        except Exception:
            return "New Chat"

    # ── Model Management ──────────────────────────────────────────────────

    def download_model(self, repo_id: str, filename: str = "", format: str = "gguf") -> Dict:
        """Download a model from HuggingFace Hub.
        
        For GGUF: downloads a single .gguf file.
        For SafeTensors: downloads the entire repo/snapshot.
        """
        try:
            from huggingface_hub import hf_hub_download, snapshot_download
        except ImportError:
            return {"status": "error", "error": "huggingface-hub not installed. Run: pip install huggingface-hub"}

        if format == "safetensors":
            return self._download_hf_repo(repo_id)
        else:
            return self._download_gguf(repo_id, filename)

    def _download_gguf(self, repo_id: str, filename: str) -> Dict:
        """Download a single GGUF file from HuggingFace Hub."""
        try:
            from huggingface_hub import hf_hub_download

            if not filename:
                return {"status": "error", "error": "filename is required for GGUF downloads"}

            print(f"  [LLM] Downloading {repo_id}/{filename}…")
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=self.models_dir,
                local_dir_use_symlinks=False,
            )
            # Move to models root if nested
            dest = os.path.join(self.models_dir, filename)
            if path != dest and os.path.isfile(path):
                shutil.move(path, dest)
                path = dest

            # Clean up empty subdirectories
            for d in Path(self.models_dir).iterdir():
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()

            size = os.path.getsize(path)
            print(f"  [LLM] ✓ Downloaded {filename} ({size / 1e9:.1f} GB)")
            return {"status": "ok", "name": filename, "path": path, "size": size, "format": "gguf"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _download_hf_repo(self, repo_id: str) -> Dict:
        """Download an entire HuggingFace model repo (SafeTensors)."""
        try:
            from huggingface_hub import snapshot_download

            # Use the repo name as directory name
            dir_name = repo_id.split("/")[-1] if "/" in repo_id else repo_id
            dest_dir = os.path.join(self.models_dir, dir_name)

            print(f"  [LLM] Downloading SafeTensors model: {repo_id}…")
            print(f"  [LLM]   → {dest_dir}")

            snapshot_download(
                repo_id=repo_id,
                local_dir=dest_dir,
                local_dir_use_symlinks=False,
                ignore_patterns=["*.md", "*.txt", "*.ot", "coreml/*", "onnx/*", "flax_model*", "tf_model*", "rust_model*"],
            )

            # Calculate total size
            total_size = sum(f.stat().st_size for f in Path(dest_dir).rglob("*") if f.is_file())
            print(f"  [LLM] ✓ Downloaded {dir_name} ({total_size / 1e9:.1f} GB)")
            return {
                "status": "ok",
                "name": dir_name,
                "path": dest_dir,
                "size": total_size,
                "format": "safetensors",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _find_model_dir_from_file(self, filepath: str) -> Optional[str]:
        """Given a .safetensors file, walk up to find the model directory (containing config.json)."""
        parent = os.path.dirname(filepath)
        if os.path.isfile(os.path.join(parent, "config.json")):
            return parent
        grandparent = os.path.dirname(parent)
        if os.path.isfile(os.path.join(grandparent, "config.json")):
            return grandparent
        return None

    def import_model(self, source_path: str) -> Dict:
        """Import a local GGUF file, SafeTensors directory, or single .safetensors file."""
        source_path = source_path.rstrip("/")

        # ── Directory (SafeTensors) ──
        if os.path.isdir(source_path):
            config = os.path.join(source_path, "config.json")
            if not os.path.isfile(config):
                # Check nested one level down (common in zip extractions)
                configs = list(Path(source_path).rglob("config.json"))
                if configs:
                    source_path = str(configs[0].parent)
                else:
                    return {"status": "error", "error": "Directory does not contain config.json — not a valid HuggingFace model"}

            dirname = os.path.basename(source_path)
            dest = os.path.join(self.models_dir, dirname)

            if os.path.abspath(source_path) == os.path.abspath(dest):
                return {"status": "ok", "name": dirname, "format": "safetensors", "note": "Already in models directory"}

            shutil.copytree(source_path, dest, dirs_exist_ok=True)
            total_size = sum(f.stat().st_size for f in Path(dest).rglob("*") if f.is_file())
            print(f"  [LLM] Imported SafeTensors model: {dirname} ({total_size / 1e9:.1f} GB)")
            return {"status": "ok", "name": dirname, "path": dest, "size": total_size, "format": "safetensors"}

        # ── Single .safetensors file → find its parent model directory ──
        if os.path.isfile(source_path) and source_path.lower().endswith((".safetensors", ".bin")):
            model_dir = self._find_model_dir_from_file(source_path)
            if model_dir:
                dirname = os.path.basename(model_dir)
                dest = os.path.join(self.models_dir, dirname)

                if os.path.abspath(model_dir) == os.path.abspath(dest):
                    return {"status": "ok", "name": dirname, "format": "safetensors", "note": "Already in models directory"}

                shutil.copytree(model_dir, dest, dirs_exist_ok=True)
                total_size = sum(f.stat().st_size for f in Path(dest).rglob("*") if f.is_file())
                print(f"  [LLM] Imported SafeTensors model: {dirname} ({total_size / 1e9:.1f} GB)")
                return {"status": "ok", "name": dirname, "path": dest, "size": total_size, "format": "safetensors"}
            else:
                return {
                    "status": "error",
                    "error": "Cannot import a standalone weight file. Transformers requires config.json and "
                             "tokenizer.json to be in the same folder. Please download the full model using "
                             "the 'Download from HuggingFace' tab in the app UI."
                }

        # ── File (GGUF) ──
        if not os.path.isfile(source_path):
            return {"status": "error", "error": f"Path not found: {source_path}"}
        if not source_path.lower().endswith(".gguf"):
            return {
                "status": "error",
                "error": "Unsupported format. Supported: .gguf files, .safetensors files (within a model folder), "
                         "or HuggingFace model directories containing config.json"
            }

        filename = os.path.basename(source_path)
        dest = os.path.join(self.models_dir, filename)

        if os.path.abspath(source_path) == os.path.abspath(dest):
            return {"status": "ok", "name": filename, "format": "gguf", "note": "Already in models directory"}

        shutil.copy2(source_path, dest)
        size = os.path.getsize(dest)
        print(f"  [LLM] Imported {filename} ({size / 1e9:.1f} GB)")
        return {"status": "ok", "name": filename, "path": dest, "size": size, "format": "gguf"}

    def delete_model(self, model_name: str) -> Dict:
        """Delete a GGUF file or SafeTensors directory from the models directory."""
        path = os.path.join(self.models_dir, model_name)

        # Unload if this is the active model
        if self._loaded_path == path:
            self.unload_model()

        # Directory (SafeTensors)
        if os.path.isdir(path):
            shutil.rmtree(path)
            print(f"  [LLM] Deleted SafeTensors model: {model_name}")
            return {"status": "ok", "name": model_name}

        # File (GGUF)
        if os.path.isfile(path):
            os.remove(path)
            print(f"  [LLM] Deleted {model_name}")
            return {"status": "ok", "name": model_name}

        return {"status": "error", "error": f"Model not found: {model_name}"}

    def get_loaded_model(self) -> Optional[str]:
        """Return the name of the currently loaded model, or None."""
        return self._loaded_model if self._llm is not None else None

    def get_loaded_info(self) -> Optional[Dict]:
        """Return info about the currently loaded model."""
        if self._llm is None:
            return None
        return {
            "name": self._loaded_model,
            "format": self._backend,
            "path": self._loaded_path,
        }


def _guess_quant(filename: str) -> str:
    """Extract quantization level from GGUF filename convention."""
    name = filename.upper()
    for q in ["Q2_K", "Q3_K_S", "Q3_K_M", "Q3_K_L", "Q4_0", "Q4_K_S", "Q4_K_M",
              "Q5_0", "Q5_K_S", "Q5_K_M", "Q6_K", "Q8_0", "F16", "F32",
              "IQ2_XXS", "IQ2_XS", "IQ3_XXS", "IQ3_XS", "IQ4_NL", "IQ4_XS"]:
        if q in name:
            return q
    return ""


# Singleton
local_llm = LocalLLM()

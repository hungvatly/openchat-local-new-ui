"""
OpenChat Local — Voice Input (Whisper)
Speech-to-text using faster-whisper for local transcription.
Falls back to whisper (openai) if faster-whisper is not available.
"""
import os
import tempfile
import time
from typing import Dict, Optional


_whisper_model = None
_whisper_backend = None


def _load_model():
    """Lazy-load whisper model on first use."""
    global _whisper_model, _whisper_backend

    if _whisper_model is not None:
        return

    model_size = os.getenv("WHISPER_MODEL", "tiny")

    # Try faster-whisper first (much faster on CPU)
    try:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
        )
        _whisper_backend = "faster-whisper"
        print(f"  [Voice] Loaded faster-whisper ({model_size})")
        return
    except ImportError:
        pass

    # Fallback to openai whisper
    try:
        import whisper
        _whisper_model = whisper.load_model(model_size)
        _whisper_backend = "openai-whisper"
        print(f"  [Voice] Loaded openai-whisper ({model_size})")
        return
    except ImportError:
        pass

    print("  [Voice] No whisper library found. Install: pip install faster-whisper")


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> Dict:
    """Transcribe audio bytes to text."""
    _load_model()

    if _whisper_model is None:
        return {
            "status": "error",
            "message": "Whisper not installed. Run: pip install faster-whisper",
        }

    # Save to temp file
    ext = os.path.splitext(filename)[1] or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp.write(audio_bytes)
    tmp.close()

    try:
        start = time.time()

        if _whisper_backend == "faster-whisper":
            segments, info = _whisper_model.transcribe(
                tmp.name,
                beam_size=1,
                language=None,  # auto-detect
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments)
            lang = info.language
        else:
            result = _whisper_model.transcribe(tmp.name)
            text = result.get("text", "").strip()
            lang = result.get("language", "")

        elapsed = round(time.time() - start, 2)

        return {
            "status": "ok",
            "text": text,
            "language": lang,
            "duration_sec": elapsed,
            "backend": _whisper_backend,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        os.unlink(tmp.name)


def is_available() -> bool:
    """Check if whisper is available."""
    try:
        import faster_whisper
        return True
    except ImportError:
        pass
    try:
        import whisper
        return True
    except ImportError:
        pass
    return False

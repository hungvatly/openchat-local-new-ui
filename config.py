"""
OpenChat Local — Configuration
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "OpenChat Local"
    APP_VERSION: str = "1.0.0"
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Local LLM
    MODELS_DIR: str = os.getenv("MODELS_DIR", "./models")
    EXTRA_MODELS_DIRS: str = os.getenv("EXTRA_MODELS_DIRS", "") # Comma-separated
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "")  # auto-picks first available
    DEFAULT_N_CTX: int = int(os.getenv("N_CTX", "4096"))
    DEFAULT_N_GPU_LAYERS: int = int(os.getenv("N_GPU_LAYERS", "-1"))  # -1 = all to Metal GPU
    DEFAULT_MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "2048"))

    # Ollama
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # RAG
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chromadb")
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    TOP_K_RESULTS: int = 5

    # Web Search
    SEARXNG_URL: str = os.getenv("SEARXNG_URL", "")  # e.g. http://localhost:8888
    WEB_SEARCH_ENABLED: bool = True
    WEB_SEARCH_MAX_RESULTS: int = 5
    WEB_FETCH_MAX_CHARS: int = 3000

    # Upload
    UPLOAD_DIR: str = "./data/uploads"
    MAX_FILE_SIZE_MB: int = 50

    # Performance profile: "low", "medium", "high"
    # low  = optimized for CPU-only / low-RAM (i3, 8-20GB RAM)
    # medium = mid-range GPU (6-8GB VRAM, 16-32GB RAM)
    # high = powerful GPU (16GB+ VRAM, 32GB+ RAM)
    PERFORMANCE_PROFILE: str = os.getenv("PERFORMANCE_PROFILE", "auto")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.MODELS_DIR, exist_ok=True)


def detect_profile() -> str:
    """Auto-detect a performance profile based on available RAM."""
    if settings.PERFORMANCE_PROFILE != "auto":
        return settings.PERFORMANCE_PROFILE
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        if ram_gb < 12:
            return "low"
        elif ram_gb < 28:
            return "medium"
        else:
            return "high"
    except ImportError:
        return "medium"


PROFILE = detect_profile()

PROFILE_SETTINGS = {
    "low": {
        "chunk_size": 256,
        "chunk_overlap": 30,
        "top_k": 3,
        "web_fetch_chars": 2000,
        "web_results": 3,
        "recommended_models": ["Qwen2.5-1.5B Q4_K_M", "Phi-3-mini Q4_K_M", "Llama-3.2-3B Q4_K_M"],
    },
    "medium": {
        "chunk_size": 512,
        "chunk_overlap": 50,
        "top_k": 5,
        "web_fetch_chars": 3000,
        "web_results": 5,
        "recommended_models": ["Llama-3.1-8B Q4_K_M", "Mistral-7B Q4_K_M", "Qwen2.5-7B Q4_K_M"],
    },
    "high": {
        "chunk_size": 768,
        "chunk_overlap": 80,
        "top_k": 8,
        "web_fetch_chars": 5000,
        "web_results": 8,
        "recommended_models": ["Qwen2.5-14B Q4_K_M", "Llama-3.1-70B Q4_K_M"],
    },
}

ACTIVE_PROFILE = PROFILE_SETTINGS.get(PROFILE, PROFILE_SETTINGS["medium"])

# Apply profile overrides
settings.CHUNK_SIZE = ACTIVE_PROFILE["chunk_size"]
settings.CHUNK_OVERLAP = ACTIVE_PROFILE["chunk_overlap"]
settings.TOP_K_RESULTS = ACTIVE_PROFILE["top_k"]
settings.WEB_FETCH_MAX_CHARS = ACTIVE_PROFILE["web_fetch_chars"]
settings.WEB_SEARCH_MAX_RESULTS = ACTIVE_PROFILE["web_results"]

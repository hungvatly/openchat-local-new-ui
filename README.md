# OpenChat Local

> A fully-featured, open-source, cross-platform alternative to NVIDIA's Chat with RTX.
> Chat with your documents, search the web, understand images, dictate with voice, generate Word/PDF/Excel files, fill form templates, and organize conversations — all running 100% locally on your machine.

![Python](https://img.shields.io/badge/Python-3.10--3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-000000?logo=ollama&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

---

## Table of Contents

- [What Is This?](#what-is-this)
- [Comparison with Chat with RTX](#comparison-with-chat-with-rtx)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Docker Deployment](#docker-deployment)
- [Usage Guide](#usage-guide)
- [System Requirements](#system-requirements)
- [Configuration Reference](#configuration-reference)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## What Is This?

OpenChat Local is a self-hosted AI chatbot that runs entirely on your computer. No cloud services, no API keys, no subscriptions, no data ever leaves your machine.

It connects to [Ollama](https://ollama.com/) for local LLM inference, and wraps it with a full productivity suite:

- **Chat with your documents** using RAG (retrieval-augmented generation)
- **Search the web** and use results as AI context
- **Understand images** with vision models
- **Dictate with your voice** via local Whisper speech-to-text
- **Generate documents** — Word (.docx), PDF, Excel (.xlsx)
- **Fill form templates** — upload a form once, AI fills it with your data each time
- **Full chat history** — persistent sessions, search, folders, export
- **AI personas** — switch between Translator, Code Reviewer, Email Writer, and more
- **Rich rendering** — syntax-highlighted code with copy buttons, markdown tables, LaTeX math, Mermaid diagrams
- **Text-to-speech** — AI reads responses aloud using browser speech synthesis

---

## Comparison with Chat with RTX

| Feature | NVIDIA Chat with RTX | OpenChat Local |
|---------|---------------------|----------------|
| Operating system | Windows only | **Windows, macOS, Linux** |
| GPU required | NVIDIA RTX 30+ (8GB VRAM) | **Any GPU or CPU-only** |
| Minimum VRAM | 8 GB | **0 GB (CPU mode)** |
| Document types | txt, pdf, docx, xml | **txt, pdf, docx, md, csv, xml** |
| Scanned PDF (OCR) | No | **Yes (Tesseract)** |
| YouTube transcripts | Yes | **Yes** |
| Web search | No | **Yes (DuckDuckGo + SearXNG)** |
| Image understanding | No | **Yes (vision models)** |
| Voice input | No | **Yes (Whisper)** |
| Text-to-speech | No | **Yes (browser TTS)** |
| Document generation | No | **Yes (Word, PDF, Excel)** |
| Template form filling | No | **Yes** |
| Chat history | No | **Yes (SQLite, search, export)** |
| AI personas | No | **Yes (7 built-in + custom)** |
| Conversation folders | No | **Yes** |
| Conversation search | No | **Yes (full-text)** |
| Code highlighting | No | **Yes (highlight.js + copy)** |
| Math rendering | No | **Yes (KaTeX LaTeX)** |
| Diagram rendering | No | **Yes (Mermaid)** |
| Watch folder (auto-index) | No | **Yes** |
| Choose any model | Limited | **Any Ollama model** |
| Open source | Partial | **Fully open source (MIT)** |
| Install size | ~40 GB | **~2 GB + model** |

---

## Features

### Chat & AI
- **Streaming responses** — token-by-token real-time output
- **Multiple LLM models** — switch via dropdown, supports any Ollama model
- **AI personas** — 7 built-in (Default, Translator, Code Reviewer, Email Writer, Legal Advisor, Creative Writer, Data Analyst) + create unlimited custom personas
- **Three chat modes** — "My Docs" (RAG), "Web Search", "No Context" (plain chat)

### Document Intelligence (RAG)
- **Supported formats** — `.txt`, `.pdf`, `.docx`, `.md`, `.csv`, `.xml`
- **Scanned PDF OCR** — automatically OCRs image-based PDFs using pymupdf + Tesseract
- **YouTube transcripts** — paste a URL to index video content
- **Watch folder** — auto-monitors a directory, indexes new/changed files every 60 min with manual "Scan now" button
- **Persistent index** — ChromaDB vector store survives restarts

### Web Search
- **DuckDuckGo** — works out of the box, no API key
- **SearXNG** — optional self-hosted multi-engine privacy search (Google, Bing, Brave, DuckDuckGo aggregated)
- **Full page fetch** — reads actual page content, not just snippets

### Image Understanding
- **Vision models** — moondream (1.8B, CPU-friendly), llava (7B), llama3.2-vision (11B)
- **Attach & ask** — upload a photo and ask questions about it
- **Zero extra dependencies** — uses Ollama's native multimodal API

### Voice Input
- **Local Whisper** — faster-whisper for CPU-optimized transcription
- **90+ languages** — auto-detects spoken language
- **Model sizes** — `tiny` (fastest), `base`, `small`, `medium`

### Document Generation
- **Word (.docx)** — formatted with headings, lists, paragraphs
- **PDF** — auto-layout with headers and sections
- **Excel (.xlsx)** — tables with styled headers, auto-width columns
- **Auto-detection** — AI detects creation intent from your message
- **Download links** — appear inline below the AI response

### Template Form Filling
- **Upload any form** — Word, PDF, or text template
- **AI analyzes structure** — detects fields, tables, sections, placeholders
- **Fill with your data** — provide information, AI generates a completed document matching the template layout
- **Reusable** — save templates for repeated use with different data

### Chat History & Organization
- **SQLite persistence** — all conversations saved automatically
- **Expandable sidebar** — shows sessions grouped by Today, Yesterday, This Week, etc.
- **Create / rename / delete** sessions
- **Conversation folders** — organize chats by project
- **Full-text search** — SQLite FTS5 search across all messages
- **Export** — download any conversation as Markdown (.md) or PDF

### Rich Rendering
- **Markdown** — tables, headings, bold, italic, lists rendered properly (marked.js)
- **Code highlighting** — syntax coloring for 180+ languages (highlight.js) with language label and Copy button
- **LaTeX math** — inline `$...$` and block `$$...$$` rendered via KaTeX
- **Mermaid diagrams** — code blocks with `mermaid` language render as SVG diagrams

### Text-to-Speech
- **Browser TTS** — zero dependencies, uses Web Speech API
- **Toggle button** — click speaker icon to enable/disable
- **Smart cleanup** — strips markdown/code from speech for natural reading

### Performance
- **Auto-tuning** — detects system RAM, adjusts chunk sizes and retrieval limits
- **Three profiles** — `low` (CPU, ≤20GB RAM), `medium` (6-8GB VRAM), `high` (16GB+ VRAM)
- **Tested on low-end hardware** — Intel i3-6100, 20GB DDR4, no GPU

---

## Architecture

```
┌────────────────┐     ┌──────────────────────────────┐     ┌────────────────┐
│                │     │        FastAPI Server         │     │                │
│    Browser     │────▶│                              │────▶│     Ollama     │
│    (Dark UI)   │◀────│  Chat, RAG, Web, Voice, Docs │◀────│   (LLM Host)  │
│                │     │                              │     │                │
└────────────────┘     └─────┬────┬────┬────┬────┬────┘     └────────────────┘
                             │    │    │    │    │
                    ┌────────┘    │    │    │    └────────┐
                    │             │    │    │             │
              ┌─────▼──┐   ┌─────▼┐  ┌▼────▼─┐   ┌──────▼─────┐
              │ChromaDB│   │SQLite│  │Web    │   │  Template  │
              │  RAG   │   │Chats │  │Search │   │  Engine    │
              │  Index  │   │History│  │DuckDDG│   │  (Forms)   │
              └────────┘   │Personas│  │SearXNG│   └────────────┘
                           └───────┘  └───────┘
              ┌────────┐   ┌───────┐   ┌────────────┐
              │ Folder │   │  Doc  │   │  Whisper   │
              │Watcher │   │ Gen   │   │  (Voice)   │
              │(Auto)  │   │DOCX/  │   │  faster-   │
              └────────┘   │PDF/XLS│   │  whisper   │
                           └───────┘   └────────────┘
```

---

## Quick Start

### Prerequisites

1. **Python 3.10–3.12** — [download](https://www.python.org/downloads/) (avoid 3.13+ for now)
2. **Ollama** — [ollama.com/download](https://ollama.com/download) (Windows) or `curl -fsSL https://ollama.com/install.sh | sh` (macOS/Linux)
3. **Pull a model:**
   ```bash
   # Low-end (no GPU, 8–20GB RAM) — ~1GB download
   ollama pull qwen2.5:1.5b

   # Mid-range (6–8GB VRAM) — ~4.7GB download
   ollama pull llama3.1:8b

   # High-end (16GB+ VRAM) — ~8.5GB download
   ollama pull qwen2.5:14b
   ```

### Install

```bash
git clone https://github.com/your-username/openchat-local.git
cd openchat-local

python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate         # Windows PowerShell

pip install -r requirements.txt
```

### Configure

Create a `.env` file:
```env
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=qwen2.5:1.5b
PERFORMANCE_PROFILE=auto
```

Set watch folder (in terminal, not .env):
```bash
export WATCH_FOLDER="$HOME/Documents"         # macOS / Linux
# $env:WATCH_FOLDER = "C:\Users\You\Documents"  # Windows PowerShell
```

### Run

```bash
python main.py
```

Open **http://localhost:8000** in your browser.

### Optional Features

```bash
# Scanned PDF OCR support
pip install pymupdf pytesseract Pillow
brew install tesseract          # macOS
# sudo apt install tesseract-ocr  # Linux

# Voice input
pip install faster-whisper

# Image understanding (pull a vision model)
ollama pull moondream           # 1.8B, CPU-friendly
```

---

## Docker Deployment

```bash
git clone https://github.com/your-username/openchat-local.git
cd openchat-local
docker compose up -d --build
```

Open **http://localhost:8000**. SearXNG at **http://localhost:8888**.

The model is pulled automatically on first start.

### Docker Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_MODEL` | `qwen2.5:1.5b` | LLM model |
| `WATCH_FOLDER_HOST` | `./_watch` | Host folder to auto-index |
| `PERFORMANCE_PROFILE` | `low` | Performance profile |
| `APP_PORT` | `8000` | Web UI port |
| `SEARXNG_PORT` | `8888` | SearXNG port |

### GPU in Docker

- **NVIDIA** — uncomment GPU section in `docker-compose.yml`, install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- **AMD** — uncomment AMD section (requires ROCm)
- **Apple Silicon** — run Ollama natively (not in Docker) for Metal acceleration

---

## Usage Guide

### Chat Modes

| Mode | What it does |
|------|-------------|
| **My Docs** | Searches indexed documents, uses matches as AI context |
| **Web Search** | Searches the web, reads top pages, feeds content to AI |
| **No Context** | Plain LLM chat without any retrieval |

### Documents
Click the **Documents** button in the sidebar. Options:
- **Watch folder** — auto-monitors and indexes new files (60 min interval + manual scan)
- **Upload files** — individual file upload
- **Index folder** — one-time folder import
- **YouTube** — paste URL to index transcript

Supported: `.txt`, `.pdf` (including scanned with OCR), `.docx`, `.md`, `.csv`, `.xml`

### Image Understanding
1. Click **Image** button in input bar
2. Select a photo
3. Type question, make sure a vision model is selected (moondream, llava)
4. Send

### Voice Input
1. Click **microphone** button — recording starts
2. Click again to stop
3. Transcribed text appears in input box
4. Edit or send directly

### Document Generation
Ask naturally:
- *"Create a Word document about project management"*
- *"Make a PDF report on AI trends"*
- *"Create a spreadsheet comparing programming languages"*

Download link appears below the AI response.

### Template Form Filling
1. Click **Templates** button in sidebar
2. Upload a form/template (.docx, .pdf, .txt)
3. Select the template, enter fill instructions
4. Click "Generate .docx" or "Generate .pdf"
5. Download the completed document

### Personas
Select a persona from the dropdown next to the send button:
- **Default** — comprehensive general assistant
- **Translator** — accurate multi-language translation
- **Code Reviewer** — bug detection, security, style suggestions
- **Email Writer** — professional email composition
- **Legal Advisor** — legal research and document analysis
- **Creative Writer** — stories, poems, creative content
- **Data Analyst** — data interpretation and insights

Create custom personas via the API.

### Chat Sessions
- **New Chat** — button at top of sidebar
- **Rename** — hover session, click pencil icon, edit inline
- **Delete** — hover session, click trash icon
- **Folders** — hover session, click folder icon to organize
- **Search** — type in sidebar search bar to find any past message
- **Filter** — use folder dropdown to filter sessions
- **Export** — History panel lets you export as .md or .pdf

### Text-to-Speech
Click the **speaker** button next to the send button. When enabled, AI reads its responses aloud. Click again to disable.

### Code Blocks
AI responses with code get:
- Syntax highlighting for 180+ languages
- Language label in top-left
- **Copy** button in top-right
- Dark theme matching the UI

### Math & Diagrams
- Inline math: `$E = mc^2$` renders as formatted equation
- Block math: `$$\int_0^\infty e^{-x} dx = 1$$` renders centered
- Mermaid: code blocks with language `mermaid` render as SVG diagrams

---

## System Requirements

| Tier | RAM | GPU | Models | Speed |
|------|-----|-----|--------|-------|
| Minimum | 8 GB | None (CPU) | 1.5B–3B | ~5–12 tok/s |
| Recommended | 16–32 GB | 6–8 GB VRAM | 7B–8B | ~25–45 tok/s |
| Optimal | 32–64 GB | 16–24 GB VRAM | 14B–70B | ~30–80 tok/s |

**Compatible GPUs:** NVIDIA (GTX 10-series+), AMD (RX 5000+), Intel Arc, Apple Silicon (M1+)

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `DEFAULT_MODEL` | `llama3.1:8b` | Default LLM model |
| `CHROMA_PERSIST_DIR` | `./data/chromadb` | Vector DB + chat history storage |
| `UPLOAD_DIR` | `./data/uploads` | Uploaded file storage |
| `MAX_FILE_SIZE_MB` | `50` | Max upload size |
| `SEARXNG_URL` | _(empty)_ | SearXNG URL (empty = DuckDuckGo) |
| `PERFORMANCE_PROFILE` | `auto` | `auto`, `low`, `medium`, `high` |
| `WATCH_FOLDER` | _(empty)_ | Folder to auto-monitor (set as env var, not in .env) |
| `WATCH_INTERVAL` | `3600` | Auto-scan interval in seconds |
| `WHISPER_MODEL` | `tiny` | Whisper model size for voice |

> **Note:** `WATCH_FOLDER` and `WATCH_INTERVAL` should be set as environment variables, not in `.env`, to avoid Pydantic validation errors on older versions.

---

## API Reference

Full REST API at `http://localhost:8000/api/`. All endpoints return JSON.

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | System status, feature flags, profile |
| `GET` | `/api/models` | Available Ollama models |

### Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat` | Send message (SSE stream). Body: `message`, `model`, `mode`, `history`, `conversation_id`, `images`, `persona_id` |

### Chat History
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/conversations` | List conversations. Query: `?folder=X&tag=Y` |
| `GET` | `/api/conversations/{id}` | Get conversation with all messages |
| `PATCH` | `/api/conversations/{id}` | Rename: `{"title": "..."}` |
| `DELETE` | `/api/conversations/{id}` | Delete conversation |
| `PATCH` | `/api/conversations/{id}/meta` | Set folder/tags/persona: `{"folder": "...", "tags": "..."}` |
| `GET` | `/api/conversations/{id}/export?format=md\|pdf` | Export conversation |
| `GET` | `/api/conversations/search/{query}` | Full-text search across all messages |

### Organization
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/folders` | List all folder names |
| `GET` | `/api/tags` | List all tags |

### Personas
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/personas` | List all personas (built-in + custom) |
| `GET` | `/api/personas/{id}` | Get persona details |
| `POST` | `/api/personas` | Create custom: `{"name": "...", "prompt": "..."}` |
| `DELETE` | `/api/personas/{id}` | Delete custom persona |

### Documents (RAG)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/documents/upload` | Upload and index a file (multipart) |
| `POST` | `/api/documents/folder` | Index all files in a folder: `{"folder_path": "..."}` |
| `POST` | `/api/documents/youtube` | Index YouTube transcript: `{"url": "..."}` |
| `GET` | `/api/documents/stats` | Number of indexed chunks |
| `POST` | `/api/documents/clear` | Clear all indexed documents |

### Folder Watcher
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/watcher/status` | Watcher status, tracked files, scan time |
| `POST` | `/api/watcher/add` | Add watch folder: `{"folder": "..."}` |
| `POST` | `/api/watcher/remove` | Remove watch folder |
| `POST` | `/api/watcher/scan` | Trigger immediate scan |

### Web Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/search` | Search web: `{"query": "..."}` |
| `POST` | `/api/search/fetch` | Fetch URL content: `{"url": "..."}` |

### Document Generation
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/generate/docx` | Generate Word: `{"title": "...", "content": "..."}` |
| `POST` | `/api/generate/pdf` | Generate PDF |
| `POST` | `/api/generate/xlsx` | Generate Excel |

### Templates
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/templates/upload` | Upload template (multipart) |
| `GET` | `/api/templates` | List saved templates |
| `GET` | `/api/templates/{id}` | Get template with detected fields |
| `DELETE` | `/api/templates/{id}` | Delete template |
| `POST` | `/api/templates/{id}/fill` | AI fills template: `{"instructions": "...", "output_format": ".docx"}` |

### Image & Voice
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload/image` | Upload image, returns base64 |
| `POST` | `/api/voice/transcribe` | Transcribe audio file |
| `GET` | `/api/voice/status` | Check Whisper availability |

---

## Project Structure

```
openchat-local/
├── main.py                     # FastAPI server — all 40+ API routes
├── config.py                   # Settings, performance profiles, auto-detection
├── requirements.txt            # Python dependencies
├── .env.example                # Configuration template
├── Dockerfile                  # Container build
├── docker-compose.yml          # Full stack: Ollama + App + SearXNG
├── docker-compose.portainer.yml # Portainer-ready stack
├── setup.bat                   # One-click Docker setup (Windows)
├── setup.sh                    # One-click Docker setup (Linux/macOS)
├── CHANGELOG.md                # Version history
├── LICENSE                     # MIT License
│
├── utils/
│   ├── ollama_client.py        # Ollama API (streaming, vision, personas)
│   ├── rag_engine.py           # ChromaDB vector store & RAG pipeline
│   ├── document_loader.py      # File parsers (PDF+OCR, DOCX, TXT, CSV, YouTube)
│   ├── web_search.py           # Web search (DuckDuckGo + SearXNG)
│   ├── folder_watcher.py       # Background folder monitor & auto-indexer
│   ├── chat_history.py         # SQLite: conversations, personas, folders, FTS5 search
│   ├── doc_generator.py        # Word (.docx), PDF, Excel (.xlsx) generation
│   ├── template_engine.py      # Template analysis, field detection, AI form filling
│   └── voice_input.py          # Whisper speech-to-text
│
├── templates/
│   └── index.html              # Main HTML (CDN: highlight.js, marked.js, KaTeX, Mermaid)
│
└── static/
    ├── css/style.css            # Dark theme + code blocks + mermaid + math styles
    └── js/app.js                # Frontend: chat, sessions, search, personas, TTS, voice, images
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot connect to Ollama" | Run `ollama list`. Windows: check system tray. Linux: `ollama serve` |
| Rust compilation error on pip | Use Python 3.12 (not 3.13+) |
| "Extra inputs are not permitted" | Set `WATCH_FOLDER` as env var, not in `.env`. Or update `config.py` with `extra = "ignore"` |
| Scanned PDF not indexing | Install `pip install pymupdf pytesseract Pillow` + `brew install tesseract` |
| Watcher skips a file | Delete `./data/chromadb/_watch_state.json` and click "Scan now" |
| Slow responses | Use smaller model (`qwen2.5:1.5b`), set `PERFORMANCE_PROFILE=low` |
| Voice button does nothing | `pip install faster-whisper`, allow mic in browser |
| Images not understood | Pull vision model: `ollama pull moondream`, select it in dropdown |
| Web search empty | Set up SearXNG: `docker run -d -p 8888:8080 searxng/searxng:latest` |
| Template returns no fields | The AI reads raw text structure — try a .docx with clear `Label: ___` fields |
| TTS not working | Check browser supports Web Speech API (Chrome, Edge, Safari do) |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -m "Add my feature"`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

Please open an issue first for major changes.

---

## Acknowledgments

- [Ollama](https://ollama.com/) — local LLM inference
- [FastAPI](https://fastapi.tiangolo.com/) — web framework
- [ChromaDB](https://www.trychroma.com/) — vector database
- [SearXNG](https://github.com/searxng/searxng) — privacy metasearch
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — speech-to-text
- [highlight.js](https://highlightjs.org/) — code syntax highlighting
- [marked.js](https://marked.js.org/) — markdown rendering
- [KaTeX](https://katex.org/) — LaTeX math rendering
- [Mermaid](https://mermaid.js.org/) — diagram rendering
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — YouTube transcripts

---

## License

MIT License — see [LICENSE](LICENSE).

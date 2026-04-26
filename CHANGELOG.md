# Changelog

All notable changes to OpenChat Local are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [2.1.0] - 2026-04-12

### Added — AI Memory
- **Persistent memory store** — save key-value facts about yourself ("Job: Engineer", "Language: Vietnamese"). Stored in SQLite.
- **Automatic injection** — every conversation starts with your memory facts appended to the system prompt, so the AI always "knows" you.
- **Memory panel** — new "Memory" button in sidebar tools opens a CRUD panel to add/delete memories.
- **API endpoints** — `GET /api/memory`, `POST /api/memory`, `DELETE /api/memory/{key}`.

### Added — Document Digest
- **One-click digest button** in the Documents panel — "Summarize All Documents" streams a structured AI digest of everything indexed.
- **API endpoint** — `POST /api/documents/digest` (streaming SSE).

### Added — Slash Commands
- **7 slash commands** — type `/` in the input box to get an autocomplete picker: `/translate`, `/summarize`, `/email`, `/code`, `/explain`, `/legal`, `/digest`.
- **Auto-switches persona** — selecting a command activates the matching persona and pre-fills the prompt hint.
- **Keyboard navigation** — Arrow keys + Enter + Escape fully keyboard-accessible.

### Added — Multi-Model Comparison
- **Compare toggle** in input bar — splits the chat into two side-by-side columns.
- **Model selector bar** — choose Model A and Model B from your installed Ollama models.
- **Parallel streaming** — both models respond simultaneously using `POST /api/chat/compare` (async asyncio queues).
- **Mobile stacks vertically** for readability on small screens.

### Added — Mobile-Responsive / PWA
- **Sidebar overlay on mobile** — sidebar slides in as an overlay with a backdrop tap-to-close on ≤768px screens.
- **Touch targets** — buttons meet 44px minimum for iOS/Android usability.
- **manifest.json** — PWA manifest with name, colors, standalone display mode.
- **Service worker** (`sw.js`) — caches static assets for fast loads and offline splash on local network.
- **Meta tags** — theme-color, description, manifest link added to `<head>`.
- **Responsive input bar** — wraps on very small screens (≤480px).

---

## [2.0.0] - 2026-04-07

### Added — Rich Rendering
- **Markdown rendering** via marked.js — tables, headings, bold, italic, lists render as proper HTML instead of raw text.
- **Code syntax highlighting** via highlight.js — 180+ languages with proper coloring, language label, and **Copy** button on every code block.
- **LaTeX math rendering** via KaTeX — inline `$...$` and block `$$...$$` display as formatted equations.
- **Mermaid diagram rendering** — code blocks with `mermaid` language render as SVG flowcharts, sequence diagrams, etc.

### Added — System Prompt Personas
- **7 built-in personas** — Default, Translator, Code Reviewer, Email Writer, Legal Advisor, Creative Writer, Data Analyst. Each changes the AI's behavior and expertise.
- **Persona selector** dropdown in the input bar — choose per conversation.
- **Custom personas** — create unlimited custom personas via the API (`POST /api/personas`).
- **Personas stored in SQLite** — persist across restarts.
- **Persona per conversation** — each conversation remembers which persona was used.

### Added — Conversation Search
- **Full-text search** across all past messages using SQLite FTS5.
- **Search bar** in the sidebar — type 2+ characters to search.
- **Results show** conversation title and matching message preview.
- **LIKE fallback** — works even if the SQLite build doesn't support FTS5.
- **API endpoint** — `GET /api/conversations/search/{query}`.

### Added — Conversation Folders & Tags
- **Folder assignment** — hover a session in sidebar, click folder icon, enter folder name.
- **Folder filter** — dropdown below search bar filters sessions by folder.
- **Tags** — assign comma-separated tags to conversations via API.
- **Folder badge** — sessions show their folder name inline.
- **API endpoints** — `GET /api/folders`, `GET /api/tags`, `PATCH /api/conversations/{id}/meta`.

### Added — Text-to-Speech
- **Speaker button** next to send — toggle TTS on/off.
- **Browser Speech API** — zero dependencies, works in Chrome, Edge, Safari.
- **Smart text cleanup** — strips markdown, code blocks, and formatting before speaking.
- **Chunked speech** — splits long responses for reliable playback.

### Changed
- **renderMarkdown()** completely rewritten to use marked.js with custom renderer.
- **Code blocks** now wrapped in `.code-block` container with language label and copy button.
- **Chat state** now includes `personaId` and `ttsEnabled`.
- **Chat API** now accepts `persona_id` parameter.
- **Ollama client** `stream_chat()` now accepts `system_prompt` parameter for persona support.
- **Sidebar** now includes search bar and folder filter dropdown.
- **Input bar** now includes persona selector and TTS toggle button.

### Fixed
- **load_pdf()** now uses pymupdf as primary reader with OCR fallback via pytesseract for scanned PDFs. Falls back to PyPDF2 as last resort. Previously returned error strings that polluted the index.

---

## [1.5.0] - 2026-04-06

### Added
- **Template-based document generation** — upload a form/template, AI analyzes its structure (fields, tables, sections), then generates a new document filled with your data.
- **Template storage** — templates persist in `data/templates/` with metadata.
- **Field auto-detection** — detects colon-separated fields (`Label: ___`), underscored blanks, bracketed placeholders, and table structures.
- **Template UI panel** — sidebar button opens Templates panel for upload, selection, and filling.
- **API endpoints** — `POST /api/templates/upload`, `GET /api/templates`, `GET /api/templates/{id}`, `DELETE /api/templates/{id}`, `POST /api/templates/{id}/fill`.
- **New file** — `utils/template_engine.py`.

### Added — Chat Sessions Sidebar
- **Expandable sidebar** — 260px wide with full chat session list, collapsible to 56px icon bar.
- **Sessions grouped by date** — Today, Yesterday, This Week, This Month, Older.
- **Inline rename** — click pencil icon, edit title, press Enter.
- **Delete with confirmation** — click trash icon.
- **Active session highlighting** — current conversation visually marked.
- **Sidebar tools** — Documents, Templates, Settings buttons in sidebar footer.
- **PATCH endpoint** — `PATCH /api/conversations/{id}` for renaming.

---

## [1.4.0] - 2026-04-06

### Added
- **Chat history persistence** — SQLite database stores all conversations and messages.
- **Conversation export** — Markdown (.md) and PDF download.
- **Document generation (Word)** — AI generates .docx files from chat.
- **Document generation (PDF)** — AI generates formatted PDFs.
- **Document generation (Excel)** — AI generates .xlsx files with styled tables.
- **Auto-detection** — document creation triggers from natural language intent.
- **Image understanding** — attach photos, send to vision models (moondream, llava).
- **Voice input** — microphone button records audio, transcribes via faster-whisper.
- **New files** — `utils/chat_history.py`, `utils/doc_generator.py`, `utils/voice_input.py`.

---

## [1.3.0] - 2026-04-06

### Changed
- **Watch folder scan interval** changed from 10 seconds to 60 minutes (3600 seconds).
- **"Scan now" button** added for immediate manual scans.

---

## [1.2.0] - 2026-04-06

### Added
- **Watch folder** — auto-monitors a directory for new/changed documents.
- **Persistent watch state** — remembers indexed files across restarts.
- **`WATCH_FOLDER` and `WATCH_INTERVAL` environment variables.**
- **New file** — `utils/folder_watcher.py`.

---

## [1.1.0] - 2026-04-06

### Added
- **Web search** — DuckDuckGo (zero setup) + SearXNG (self-hosted).
- **Three chat modes** — My Docs, Web Search, No Context.
- **Performance auto-tuning** — detects RAM, applies optimal profile.
- **New file** — `utils/web_search.py`.

---

## [1.0.0] - 2026-04-06

### Added
- **Initial release** — local RAG chatbot with document ingestion, streaming chat, multiple models, dark theme UI.
- **Document support** — .txt, .pdf, .docx, .md, .csv, .xml.
- **YouTube transcripts** — via yt-dlp.
- **Docker support** — Dockerfile + docker-compose.yml.
- **Cross-platform** — Windows, macOS, Linux.

---

## Bugfixes Applied

| Issue | Fix |
|-------|-----|
| `pydantic-core` Rust compilation on Python 3.13+ | Removed strict version pins from requirements.txt |
| `TemplateResponse` tuple TypeError | Changed to `TemplateResponse(request, "index.html")` |
| `WATCH_FOLDER` in .env crashes Pydantic | Added `extra = "ignore"` to Settings Config |
| AI responses too short | Rewrote system prompt for detailed answers |
| Scanned PDFs return 0 text | Added pymupdf + pytesseract OCR pipeline |
| Watcher skips previously-failed files | Delete `_watch_state.json` to force re-scan |

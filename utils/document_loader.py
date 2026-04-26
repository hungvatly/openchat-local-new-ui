"""
OpenChat Local — Document Loader
Supports: .txt, .pdf, .docx, .md, .csv, .xml, YouTube URLs

PDF strategy:
  1. pymupdf  — fast text-layer extraction
  2. macOS Vision framework (pyobjc) — native OCR, no external install
  3. pytesseract — fallback if Tesseract is installed
"""
import os
import re
import subprocess
import json
import tempfile
from typing import List, Dict, Optional


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks


def load_txt(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


# ── OCR helpers ──────────────────────────────────────────────

def _ocr_via_macos_vision(image_path: str) -> str:
    """
    Use macOS Vision framework via a subprocess Swift one-liner.
    Works on macOS 10.15+ with NO external dependencies.
    """
    swift_code = f"""
import Vision
import Foundation
let url = URL(fileURLWithPath: "{image_path}")
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
let handler = VNImageRequestHandler(url: url, options: [:])
try? handler.perform([request])
let results = request.results ?? []
let text = results.compactMap {{ $0.topCandidates(1).first?.string }}.joined(separator: "\\n")
print(text)
"""
    try:
        result = subprocess.run(
            ["swift", "-"],
            input=swift_code,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"  [OCR] macOS Vision failed: {e}")
        return ""


def _ocr_page_images(pdf_path: str) -> str:
    """Convert PDF pages to images, then OCR each page."""
    try:
        import fitz  # pymupdf
        from PIL import Image
        import io

        doc = fitz.open(pdf_path)
        all_text = []

        for page_num, page in enumerate(doc):
            # Render at 200 DPI for good OCR quality
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")

            # Write to temp file for Vision framework
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(img_bytes)
                tmp_path = tmp.name

            try:
                # Try macOS Vision first (no deps needed)
                text = _ocr_via_macos_vision(tmp_path)
                if text.strip():
                    print(f"  [OCR] Vision: page {page_num+1} → {len(text)} chars")
                    all_text.append(text)
                    continue

                # Fallback: pytesseract
                try:
                    import pytesseract
                    img = Image.open(io.BytesIO(img_bytes))
                    text = pytesseract.image_to_string(img)
                    if text.strip():
                        print(f"  [OCR] Tesseract: page {page_num+1} → {len(text)} chars")
                        all_text.append(text)
                except ImportError:
                    pass
                except Exception as e:
                    print(f"  [OCR] Tesseract page {page_num+1} error: {e}")

            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        doc.close()
        return "\n".join(all_text)

    except ImportError:
        print("  [PDF] pymupdf not installed — install with: pip install pymupdf")
        return ""
    except Exception as e:
        print(f"  [OCR] Page-to-image OCR failed: {e}")
        return ""


def load_pdf(filepath: str) -> str:
    """
    3-tier PDF loading:
    1. pymupdf text extraction (fast, handles text-layer PDFs)
    2. macOS Vision OCR (for scanned/image PDFs — no deps needed)
    3. pytesseract (if installed)
    """
    # ── Tier 1: pymupdf text layer ────────────────────────────
    try:
        import fitz
        doc = fitz.open(filepath)
        text_parts = []
        for page in doc:
            t = page.get_text()
            if t.strip():
                text_parts.append(t)
        doc.close()
        text = "\n".join(text_parts)

        if text.strip() and len(text.strip()) > 50:
            print(f"  [PDF] Text layer: {len(text)} chars from {os.path.basename(filepath)}")
            return text

        print(f"  [PDF] Text layer empty/thin ({len(text.strip())} chars) — trying OCR")

    except ImportError:
        print("  [PDF] pymupdf not available, falling back")
    except Exception as e:
        print(f"  [PDF] pymupdf error: {e}")

    # ── Tier 2 & 3: OCR (Vision + Tesseract) ─────────────────
    ocr_text = _ocr_page_images(filepath)
    if ocr_text.strip():
        return ocr_text

    # ── Last resort: PyPDF2 ───────────────────────────────────
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        if text.strip():
            return text
    except Exception as e:
        print(f"  [PDF] PyPDF2 fallback failed: {e}")

    print(f"  [PDF] ⚠ Could not extract any text from {os.path.basename(filepath)}")
    return ""


def load_docx(filepath: str) -> str:
    try:
        from docx import Document
        doc = Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        return f"[Error reading DOCX: {e}]"


def load_csv(filepath: str) -> str:
    import csv
    rows = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(", ".join(row))
    return "\n".join(rows)


def load_youtube_transcript(url: str) -> Optional[str]:
    """Extract transcript from a YouTube video using yt-dlp."""
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--skip-download",
                "--sub-format", "json3",
                "-o", "/tmp/yt_transcript",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        transcript_file = "/tmp/yt_transcript.en.json3"
        if os.path.exists(transcript_file):
            with open(transcript_file, "r") as f:
                data = json.load(f)
            segments = data.get("events", [])
            text_parts = []
            for seg in segments:
                segs = seg.get("segs", [])
                for s in segs:
                    t = s.get("utf8", "").strip()
                    if t and t != "\n":
                        text_parts.append(t)
            os.remove(transcript_file)
            return " ".join(text_parts)

        vtt_file = "/tmp/yt_transcript.en.vtt"
        if os.path.exists(vtt_file):
            with open(vtt_file, "r") as f:
                content = f.read()
            lines = content.split("\n")
            text_parts = []
            for line in lines:
                line = line.strip()
                if not line or "-->" in line or line.startswith("WEBVTT") or line.isdigit():
                    continue
                clean = re.sub(r"<[^>]+>", "", line)
                if clean:
                    text_parts.append(clean)
            os.remove(vtt_file)
            return " ".join(text_parts)

        return None
    except Exception as e:
        print(f"YouTube transcript error: {e}")
        return None


LOADERS = {
    ".txt": load_txt,
    ".md":  load_txt,
    ".pdf": load_pdf,
    ".docx": load_docx,
    ".csv": load_csv,
    ".xml": load_txt,
}


def load_document(filepath: str) -> Dict:
    """Load a document and return its text content with metadata."""
    ext = os.path.splitext(filepath)[1].lower()
    loader = LOADERS.get(ext)
    if not loader:
        return {"error": f"Unsupported file type: {ext}", "text": "", "filename": os.path.basename(filepath)}

    text = loader(filepath)
    return {
        "text": text,
        "filename": os.path.basename(filepath),
        "filepath": filepath,
        "extension": ext,
        "size": os.path.getsize(filepath),
    }


def load_folder(folder_path: str) -> List[Dict]:
    """Load all supported documents from a folder."""
    documents = []
    supported_exts = set(LOADERS.keys())

    for root, dirs, files in os.walk(folder_path):
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            if ext in supported_exts:
                fpath = os.path.join(root, fname)
                doc = load_document(fpath)
                if doc.get("text"):
                    documents.append(doc)

    return documents

"""
OpenChat Local — Smart Form Filler
Two-file workflow: extract structure from a template + content from a source file,
then assemble an LLM prompt to produce a filled Markdown document.

Layer 1: File extraction (preserving table/structure metadata)
Layer 2: Prompt assembly
"""
from __future__ import annotations

import io
import os
import re
from typing import Dict, List, Tuple


# ── Layer 1: Extraction ───────────────────────────────────────────────────────

def extract_text(path: str) -> str:
    """Router: extract structured text from any supported file."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return _extract_docx(path)
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext in (".txt", ".md", ".csv"):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    # Fallback: read as text
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return "(Could not read file)"


def _extract_docx(path: str) -> str:
    """Extract text + table structure from a .docx file."""
    try:
        from docx import Document  # python-docx
        doc = Document(path)
        parts: List[str] = []

        for block in _iter_blocks(doc):
            if block["type"] == "paragraph":
                text = block["text"]
                style = block.get("style", "")
                if not text.strip():
                    continue
                if "Heading" in style:
                    level = int(style.replace("Heading ", "")) if style != "Heading" else 1
                    parts.append(f"\n{'#' * level} {text}")
                else:
                    parts.append(text)
            elif block["type"] == "table":
                rows = block["rows"]
                cols = max(len(r) for r in rows) if rows else 0
                parts.append(f"\n[TABLE: {cols} columns × {len(rows)} rows]")
                for i, row in enumerate(rows):
                    cells = " | ".join(f'"{c}"' if c else '(empty)' for c in row)
                    parts.append(f"Row {i+1}: {cells}")
                parts.append("")

        return "\n".join(parts)
    except ImportError:
        return f"(python-docx not installed — could not parse .docx)\nFile: {os.path.basename(path)}"
    except Exception as e:
        return f"(Error reading .docx: {e})"


def _iter_blocks(doc):
    """Yield paragraphs and tables in document order."""
    from docx.oxml.ns import qn
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "p":
            from docx.text.paragraph import Paragraph
            para = Paragraph(child, doc)
            yield {"type": "paragraph", "text": para.text, "style": para.style.name}
        elif tag == "tbl":
            from docx.table import Table
            table = Table(child, doc)
            rows = []
            for row in table.rows:
                rows.append([cell.text.strip() for cell in row.cells])
            yield {"type": "table", "rows": rows}


def _extract_pdf(path: str) -> str:
    """Extract text + tables from a PDF. Prefers pdfplumber for table preservation."""
    try:
        import pdfplumber
        parts: List[str] = []
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                parts.append(f"\n[PAGE {page_num}]")
                # Extract tables first
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        if not table:
                            continue
                        cols = max(len(row) for row in table)
                        parts.append(f"[TABLE: {cols} columns × {len(table)} rows]")
                        for i, row in enumerate(table):
                            cells = " | ".join(
                                f'"{(c or "").strip()}"' if (c or "").strip() else '(empty)'
                                for c in (row or [])
                            )
                            parts.append(f"Row {i+1}: {cells}")
                        parts.append("")
                # Extract remaining text (excluding table bboxes)
                text = page.extract_text() or ""
                if text.strip():
                    parts.append(text.strip())
        return "\n".join(parts)
    except ImportError:
        pass  # Fall through to pypdf

    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        pages = []
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[PAGE {i}]\n{text.strip()}")
        return "\n\n".join(pages)
    except ImportError:
        return "(No PDF library available. Install pdfplumber: pip install pdfplumber)"
    except Exception as e:
        return f"(Error reading PDF: {e})"


# ── Layer 2: Prompt Assembly ──────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a document form-filling assistant. You will receive:
1. A TEMPLATE — a blank or partially filled form/document whose structure you must follow exactly
2. CONTENT SOURCE — information, notes, or data to be inserted into the template

Your task:
- Study the template structure carefully (headings, sections, tables, field labels)
- Map the relevant content from the source into the correct fields and sections
- Output a COMPLETE filled document in clean Markdown format
- Preserve ALL headings, section labels, and table structures from the template
- For table rows: maintain the same columns, just fill in the empty cells with matching data
- If a field has no matching data in the source, write "(N/A)" — never invent information
- Do NOT include explanations, preamble, or code blocks — output the filled document ONLY
"""

_USER_PROMPT_TEMPLATE = """\
=== TEMPLATE (structure to follow) ===
{template_text}

=== CONTENT SOURCE (data to insert) ===
{content_text}

=== INSTRUCTIONS ===
Fill the template above using the content source. Output the complete filled document in Markdown format, following the template's structure exactly.
"""


def build_form_fill_prompt(template_text: str, content_text: str) -> Tuple[str, str]:
    """Return (system_prompt, user_message) pair for the LLM."""
    # Truncate to avoid context overflow (keep most important parts)
    tmpl = _truncate(template_text, 3000)
    cont = _truncate(content_text, 3000)
    user_msg = _USER_PROMPT_TEMPLATE.format(template_text=tmpl, content_text=cont)
    return _SYSTEM_PROMPT, user_msg


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [truncated — {len(text) - max_chars} more chars]"

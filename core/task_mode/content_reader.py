import os
import mimetypes
from pathlib import Path
from typing import Tuple, Dict, Any

def extract_content(filepath: str, max_chars: int = 2000) -> Tuple[str, Dict[str, Any]]:
    """
    Extracts text from files dynamically based on mimetype.
    Returns a tuple of (content_string, metadata_dict).
    Truncates text to `max_chars`.
    """
    path = Path(filepath)
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "application/octet-stream"
        
    stat = os.stat(path)
    meta = {
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "mime": mime_type
    }
    
    content = ""
    
    try:
        # Text based
        if mime_type.startswith("text/") or mime_type in ["application/json", "application/javascript", "application/xml"]:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read(max_chars + 100) # Read slightly over for truncation check
                
        # PDF
        elif mime_type == "application/pdf":
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                pages = []
                for p in pdf.pages:
                    text = p.extract_text()
                    if text:
                        pages.append(text)
                    if len("\n".join(pages)) > max_chars:
                        break
                content = "\n".join(pages)
                
        # Word
        elif mime_type in [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword"
        ]:
            import docx
            doc = docx.Document(path)
            parts = []
            for para in doc.paragraphs:
                if para.text:
                    parts.append(para.text)
                if len("\n".join(parts)) > max_chars:
                    break
            content = "\n".join(parts)
            
        # Excel
        elif mime_type in [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel"
        ]:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            ws = wb.active
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i > 10: # Only read first 10 rows
                    break
                row_str = " | ".join([str(v) for v in row if v is not None])
                if row_str:
                    rows.append(row_str)
            content = "\n".join(rows)
            wb.close()
            
        # Images
        elif mime_type.startswith("image/"):
            from PIL import Image
            from PIL.ExifTags import TAGS
            
            with Image.open(path) as img:
                meta["dimensions"] = img.size
                exif_data = img.getexif()
                if exif_data:
                    exif_strings = []
                    for tag_id, val in exif_data.items():
                        tag_name = TAGS.get(tag_id, tag_id)
                        exif_strings.append(f"{tag_name}: {val}")
                    meta["exif"] = ", ".join(exif_strings)
                    
            # Try OCR if pytesseract is installed
            try:
                import pytesseract
                # A light OCR extract
                from PIL import Image
                with Image.open(path) as img:
                    ocr_text = pytesseract.image_to_string(img)
                    content = ocr_text
            except Exception:
                # Silently fail if Tesseract OCR isn't natively available, relying only on Exif
                content = "[Image OCR not available or failed. See metadata.]"
                
    except Exception as e:
        content = f"[Error reading content: {str(e)}]"
        
    # Truncate content
    if len(content) > max_chars:
        content = content[:max_chars] + f"... [truncated, {len(content)} original chars]"
        
    return content.strip(), meta

# pdf_io.py

from pathlib import Path
from typing import Optional

try:
    import fitz  # PyMuPDF

    HAVE_PYMUPDF = True
except ImportError:
    HAVE_PYMUPDF = False


class PDFError(Exception):
    """Error processing PDF files"""

    pass


def extract_text_from_pdf(pdf_path: Path, max_pages: Optional[int] = None) -> str:
    """Extract text from PDF using PyMuPDF"""
    if not HAVE_PYMUPDF:
        raise PDFError("PyMuPDF (fitz) not available. Install with: pip install pymupdf")

    if not pdf_path.exists():
        raise PDFError(f"PDF file not found: {pdf_path}")

    try:
        doc = fitz.open(pdf_path)
        text_blocks = []

        page_limit = min(len(doc), max_pages) if max_pages else len(doc)

        for page_num in range(page_limit):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                text_blocks.append(f"=== PAGE {page_num + 1} ===\n{text}\n")

        doc.close()

        if not text_blocks:
            raise PDFError("No text found in PDF")

        return "\n".join(text_blocks)

    except Exception as e:
        raise PDFError(f"Error extracting text from PDF: {e}")

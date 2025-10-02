# pdf_io.py
"""
PDF text extraction utilities for the PDFtoPodcast extraction pipeline.

This module provides functions to extract text from PDF files using PyMuPDF (fitz),
with features designed for LLM processing:
- Page-by-page extraction with page markers for context preservation
- Optional page limit for testing and cost control
- Empty page filtering to reduce token usage
- Graceful degradation if PyMuPDF is not installed

The extracted text includes page markers (e.g., "=== PAGE 1 ===") to help LLMs
understand document structure and maintain spatial awareness during extraction.

Dependencies:
    - PyMuPDF (fitz) >= 1.23.0 - PDF parsing and text extraction
      Install with: pip install pymupdf

Example Usage:
    >>> from pathlib import Path
    >>> from src.pdf_io import extract_text_from_pdf
    >>>
    >>> # Extract all pages
    >>> pdf_path = Path("research_paper.pdf")
    >>> text = extract_text_from_pdf(pdf_path)
    >>> print(text[:100])
    === PAGE 1 ===
    Introduction
    This study investigates...
    >>>
    >>> # Extract only first 5 pages (for testing/cost control)
    >>> text = extract_text_from_pdf(pdf_path, max_pages=5)
    >>> pages = text.split("=== PAGE")
    >>> len(pages) - 1  # Subtract 1 for text before first marker
    5

Note:
    Empty pages (containing only whitespace) are automatically skipped to
    reduce token usage in downstream LLM processing.
"""

import logging
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

# Page marker template for document structure preservation
PAGE_MARKER_TEMPLATE = "=== PAGE {page_num} ==="

try:
    import fitz  # PyMuPDF

    HAVE_PYMUPDF = True
    logger.debug("PyMuPDF (fitz) available for PDF processing")
except ImportError:
    HAVE_PYMUPDF = False
    logger.warning(
        "PyMuPDF (fitz) not available. PDF extraction will fail. "
        "Install with: pip install pymupdf"
    )


class PDFError(Exception):
    """Error processing PDF files"""

    pass


def extract_text_from_pdf(pdf_path: Union[str, Path], max_pages: Optional[int] = None) -> str:
    """
    Extract text from PDF file with page markers for LLM processing.

    Extracts text page-by-page using PyMuPDF, adding page markers to preserve
    document structure. Empty pages (whitespace only) are automatically skipped
    to reduce token usage in downstream LLM processing.

    Args:
        pdf_path: Path to PDF file (str or Path object)
        max_pages: Optional limit on number of pages to extract.
                  Useful for testing or cost control with large PDFs.
                  If None, extracts all pages.

    Returns:
        Extracted text with page markers in format:
        ```
        === PAGE 1 ===
        [page 1 text]

        === PAGE 2 ===
        [page 2 text]
        ```

    Raises:
        PDFError: If PyMuPDF is not installed
        PDFError: If PDF file not found at specified path
        PDFError: If no text found in PDF (all pages empty or unsupported format)
        PDFError: If error during text extraction (corrupted PDF, etc.)

    Example:
        >>> from pathlib import Path
        >>> pdf_path = Path("paper.pdf")
        >>> text = extract_text_from_pdf(pdf_path)
        >>> # Check page count
        >>> page_count = text.count("=== PAGE")
        >>> print(f"Extracted {page_count} pages")
        >>>
        >>> # Extract first 3 pages only
        >>> preview = extract_text_from_pdf(pdf_path, max_pages=3)
    """
    # Normalize to Path object
    pdf_path = Path(pdf_path)

    if not HAVE_PYMUPDF:
        raise PDFError("PyMuPDF (fitz) not available. Install with: pip install pymupdf")

    if not pdf_path.exists():
        raise PDFError(f"PDF file not found: {pdf_path}")

    try:
        # Use context manager for automatic resource cleanup
        with fitz.open(pdf_path) as doc:
            text_blocks = []
            total_pages = len(doc)
            page_limit = min(total_pages, max_pages) if max_pages else total_pages

            logger.info(
                f"Extracting text from PDF: {pdf_path.name} " f"({page_limit}/{total_pages} pages)"
            )

            empty_pages_skipped = 0

            for page_num in range(page_limit):
                page = doc[page_num]
                text = page.get_text()

                if text.strip():
                    # Use template constant for page markers
                    page_marker = PAGE_MARKER_TEMPLATE.format(page_num=page_num + 1)
                    text_blocks.append(f"{page_marker}\n{text}\n")
                else:
                    empty_pages_skipped += 1
                    logger.debug(f"Skipping empty page {page_num + 1}")

            if not text_blocks:
                raise PDFError(
                    f"No text found in PDF (all {page_limit} pages empty or unsupported format)"
                )

            # Calculate statistics
            extracted_text = "\n".join(text_blocks)
            char_count = len(extracted_text)
            pages_extracted = len(text_blocks)

            logger.info(
                f"Successfully extracted {pages_extracted} pages "
                f"({char_count:,} characters, {empty_pages_skipped} empty pages skipped)"
            )

            return extracted_text

    except fitz.FitzError as e:
        # PyMuPDF-specific errors (corrupted PDF, unsupported features, etc.)
        logger.error(f"PyMuPDF error extracting text from {pdf_path}: {e}")
        raise PDFError(f"Error extracting text from PDF: {e}")
    except OSError as e:
        # File I/O errors (permissions, disk full, etc.)
        logger.error(f"I/O error reading PDF {pdf_path}: {e}")
        raise PDFError(f"Error reading PDF file: {e}")

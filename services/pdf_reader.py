"""PDF text extraction.

Uses ``pdfplumber`` as the primary extractor (better layout handling) and
falls back to ``PyPDF2`` if pdfplumber fails to open a malformed file.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pdfplumber
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)


class PDFReadError(Exception):
    """Raised when a PDF cannot be read by either backend."""


def extract_text_from_pdf(path: str | Path) -> str:
    """Extract plain text from a PDF file, trying pdfplumber then PyPDF2."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    try:
        return _extract_with_pdfplumber(path)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, we fall back
        logger.warning("pdfplumber failed for %s (%s); falling back to PyPDF2", path, exc)

    try:
        return _extract_with_pypdf2(path)
    except Exception as exc:  # noqa: BLE001
        raise PDFReadError(f"Could not extract text from {path}: {exc}") from exc


def _extract_with_pdfplumber(path: Path) -> str:
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            chunks.append(text)
    text = "\n".join(chunks).strip()
    if not text:
        raise ValueError("pdfplumber extracted no text")
    return text


def _extract_with_pypdf2(path: Path) -> str:
    reader = PdfReader(str(path))
    chunks = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(chunks).strip()
    if not text:
        raise ValueError("PyPDF2 extracted no text")
    return text

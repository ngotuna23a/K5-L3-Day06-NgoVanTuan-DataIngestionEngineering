"""Read and normalize source data while preserving physical page numbers."""
import re
import unicodedata
import warnings
from collections.abc import Iterable
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage


def load_pdf(
    path: Path,
    document_id: str,
    source: str,
    *,
    page_numbers: Iterable[int] | None = None,
) -> list[DocumentPage]:
    """Extract 1-based physical pages; flag empty text without inventing OCR."""
    reader = PdfReader(path)
    numbers = list(page_numbers) if page_numbers is not None else range(1, len(reader.pages) + 1)
    if any(number < 1 or number > len(reader.pages) for number in numbers):
        raise ValueError(f"Page numbers must be between 1 and {len(reader.pages)}")
    pages = []
    for number in numbers:
        try:
            text = normalize_text(reader.pages[number - 1].extract_text() or "")
        except Exception as exc:
            raise RuntimeError(f"Failed to extract {source}, PDF page {number}") from exc
        status = "ok" if text.strip() else "empty_text"
        if status == "empty_text":
            warnings.warn(f"No extractable text: {source}, PDF page {number}", stacklevel=2)
        pages.append(DocumentPage(document_id, source, number, text, {"extraction_status": status}))
    return pages


def normalize_text(text: str) -> str:
    """Normalize NFC/newlines; preserve line breaks and code indentation."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n")

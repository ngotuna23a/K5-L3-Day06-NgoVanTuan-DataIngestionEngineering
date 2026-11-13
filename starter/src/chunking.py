"""Implement fixed-size and structure-aware chunking."""
import hashlib
import re

from .models import Chunk, DocumentPage


def _chunk(page: DocumentPage, start: int, end: int, method: str) -> Chunk:
    text = page.text[start:end]
    digest = hashlib.sha256(f"{method}:{start}:{end}:{text}".encode("utf-8")).hexdigest()[:20]
    return Chunk(
        chunk_id=f"{page.document_id}:p{page.page}:{digest}",
        document_id=page.document_id, source=page.source, page=page.page, text=text,
        metadata={**page.metadata, "char_start": start, "char_end": end, "chunking": method},
    )


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split each page into overlapping character windows without crossing pages."""
    if type(size) is not int or type(overlap) is not int or size < 1 or not 0 <= overlap < size:
        raise ValueError("Require size > 0 and 0 <= overlap < size")
    chunks = []
    start = 0
    while start < len(page.text):
        end = min(start + size, len(page.text))
        if page.text[start:end].strip():
            chunks.append(_chunk(page, start, end, f"fixed:{size}:{overlap}"))
        if end == len(page.text):
            break
        start = end - overlap
    return chunks


def _heading(line: str) -> bool:
    stripped = line.strip()
    if re.match(r"^\d+\.\d+\s+\S", stripped):
        return True
    # A short title without sentence punctuation; do not classify code as a title.
    return bool(
        stripped and line == line.lstrip() and stripped[0].isupper()
        and len(stripped) <= 70 and not re.search(r"[.!?:;,=()\[\]{}\"']", stripped)
    )


def _headings_only(text: str) -> bool:
    return all(_heading(line) or line.strip().isdigit()
               for line in text.splitlines() if line.strip())


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Group source spans using blank lines, headings and list starts.

    PDF extraction often has only soft-wrapped lines, so heading detection is a
    heuristic. Oversized spans split at a newline/space, then a character limit.
    """
    if type(max_size) is not int or max_size < 1:
        raise ValueError("max_size must be positive")
    boundaries = {0, len(page.text)}
    headings = set()
    offset = 0
    for line in page.text.splitlines(keepends=True):
        if not line.strip() or _heading(line.rstrip("\r\n")):
            boundaries.add(offset)
            if line.strip():
                headings.add(offset)
        elif re.match(r"^\s*(?:•|\d+\.|[a-z]\.)\s+", line):
            boundaries.add(offset)
        offset += len(line)
    positions = sorted(boundaries)
    spans = []
    for start, end in zip(positions, positions[1:]):
        while end - start > max_size:
            limit = start + max_size
            split = page.text.rfind("\n", start, limit + 1)
            if split <= start:
                split = page.text.rfind(" ", start, limit + 1)
            cut = split + 1 if start < split < limit else limit
            spans.append((start, cut))
            start = cut
        if start < end:
            spans.append((start, end))
    grouped = []
    for start, end in spans:
        attach_heading = grouped and _headings_only(page.text[grouped[-1][0]:start])
        if grouped and (start not in headings or attach_heading) and end - grouped[-1][0] <= max_size:
            grouped[-1] = (grouped[-1][0], end)
        else:
            grouped.append((start, end))
    if len(grouped) > 1 and _headings_only(page.text[grouped[-1][0]:grouped[-1][1]]):
        if grouped[-1][1] - grouped[-2][0] <= max_size:
            grouped[-2:] = [(grouped[-2][0], grouped[-1][1])]
    return [_chunk(page, start, end, f"paragraph:{max_size}")
            for start, end in grouped if page.text[start:end].strip()]

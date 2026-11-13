"""Prepare the first two chapters of the supplied OpenStax PDF, without OCR."""
import hashlib
import json
import re
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from pypdf import PdfReader

from .ingestion import load_pdf, normalize_text


ROOT = Path(__file__).resolve().parents[2]
SOURCE = "Introduction_to_Python_Programming-WEB.pdf"
SOURCE_ID = "openstax-python-2026-ch01-02"
URL = "https://openstax.org/details/books/introduction-python-programming"
ATTRIBUTION = "Access for free at openstax.org."
LICENSE = "CC BY-NC-SA 4.0"
# Verified against the contents and bookmarks of the supplied 2026 PDF.
CHAPTERS = [(1, "Statements", 17, 46), (2, "Expressions", 47, 76)]
FOOTER = re.compile(r"^(?:\d+\s+\d+\s*•\s*.+|\d+\.\d+\s*•\s*.+\s+\d+)$")


def content_text(text: str) -> str:
    """Remove running page labels; retain attribution separately per record."""
    lines = [
        line for line in text.splitlines()
        if line.strip().rstrip(".") != ATTRIBUTION.rstrip(".")
        and not FOOTER.fullmatch(line.strip())
    ]
    return normalize_text("\n".join(lines))


def main() -> None:
    path = ROOT / SOURCE
    reader = PdfReader(path)
    expected = {"Chapter 1 Statements": 17, "Chapter 2 Expressions": 47, "Chapter 3 Objects": 77}
    bookmarks = {
        item.title: reader.get_destination_page_number(item) + 1
        for item in reader.outline if not isinstance(item, list)
    }
    if any(bookmarks.get(title) != page for title, page in expected.items()):
        raise ValueError("PDF chapter boundaries changed; review the selected page ranges.")
    license_text = normalize_text(reader.pages[3].extract_text() or "")
    if LICENSE not in license_text:
        raise ValueError("Expected license not found on PDF page 4; review the source license.")

    records, excluded = [], []
    for number, title, start, end in CHAPTERS:
        for page in load_pdf(path, SOURCE_ID, SOURCE, page_numbers=range(start, end + 1)):
            page.text = content_text(page.text)
            if not page.text.strip():
                excluded.append({"page": page.page, "reason": "No content after removing running footer."})
                continue
            # The printed page is physical page minus 10, verified from the contents/footer.
            page.metadata.update({
                "chapter": number,
                "chapter_title": title,
                "book_page": page.page - 10,
                "language": "en",
            })
            record = asdict(page)
            record.update({
                "page_id": f"{SOURCE_ID}:pdf-{page.page:03d}",
                "char_count": len(page.text),
                "attribution": ATTRIBUTION,
                "license": LICENSE,
            })
            records.append(record)
    if len(records) < 30:
        raise ValueError(f"Only {len(records)} useful pages; at least 30 are required.")

    manifest = {
        "source_id": SOURCE_ID,
        "title": "Introduction to Python Programming",
        "source_path_or_url": SOURCE,
        "source_url": URL,
        "license_or_permission": LICENSE,
        "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "license_evidence_pdf_page": 4,
        "attribution": ATTRIBUTION,
        "accessed_at": "2026-11-13",
        "accessed_at_note": "Date the supplied local file was inspected; original download date unknown.",
        "snapshot": {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pdf_creation_date": reader.metadata.get("/CreationDate"),
            "copyright_year": 2026,
            "total_physical_pages": len(reader.pages),
        },
        "chapters": [
            {"chapter": n, "title": title, "physical_page_start": start, "physical_page_end": end}
            for n, title, start, end in CHAPTERS
        ],
        "counting_method": "Count physical PDF pages with content in chapters 1-2; exclude footer-only pages. Front matter, other chapters, answer key and index are outside the selection.",
        "selected_page_count": 60,
        "useful_page_count": len(records),
        "total_normalized_characters": sum(record["char_count"] for record in records),
        "excluded_pages": excluded,
        "pages": [
            {"page_id": r["page_id"], "page": r["page"], "book_page": r["metadata"]["book_page"],
             "chapter": r["metadata"]["chapter"], "char_count": r["char_count"]}
            for r in records
        ],
        "extraction": {
            "library": "pypdf", "version": version("pypdf"), "ocr_used": False,
            "normalization": "Unicode NFC; LF newlines; NBSP to space; trim line endings; collapse extra blank lines; remove running footers; store attribution per page.",
            "sample_checked_pdf_pages": [17, 20, 24, 33, 39, 43, 46, 47, 57, 62, 73, 76],
            "sample_check_method": "Read extracted text and compare chapter/page references with PDF contents/bookmarks; no visual PDF verification performed.",
            "known_limitations": [
                "Some mathematical expressions are absent from extracted text (observed on PDF page 57); verify evidence against the original PDF.",
                "Tables and side-by-side code/output can lose layout; extracted code is reference text, not executable code.",
                "Pages can contain the end of one section and the start of another; chapter metadata is used instead of assigning a single section.",
            ],
        },
    }
    output = ROOT / "data"
    output.mkdir(exist_ok=True)
    with (output / "pages.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Prepared {len(records)} pages, {manifest['total_normalized_characters']} characters.")
    print(f"Excluded pages: {[item['page'] for item in excluded]}")
    print("Output: data/pages.jsonl, data/manifest.json")


if __name__ == "__main__":
    main()

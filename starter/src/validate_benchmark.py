"""Validate benchmark integrity/evidence without running retrieval or scoring test."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]


def normalized(text: str) -> str:
    return " ".join(text.split())


def validate_questions(
    questions: list[dict[str, Any]], pages: list[dict[str, Any]]
) -> dict[str, Any]:
    lookup = {(p["document_id"], p["page"]): p for p in pages}
    identifiers, question_texts = set(), set()
    splits, filters = Counter(), Counter()
    topics = {"dev": set(), "test": set()}
    evidence_count = 0
    for question in questions:
        identifier = question.get("id", "<missing>")

        def require(condition: bool, message: str) -> None:
            if not condition:
                raise ValueError(f"{identifier}: {message}")

        for field in ("id", "split", "type", "topic", "question", "expected_answer",
                      "gold_source_id", "evidence_quote"):
            require(isinstance(question.get(field), str) and bool(question[field].strip()),
                    f"missing or empty {field}")
        require(identifier not in identifiers, "duplicate ID")
        identifiers.add(identifier)
        text = normalized(question["question"])
        require(text not in question_texts, "duplicate question")
        question_texts.add(text)
        split = question["split"]
        require(split in topics, "split must be dev or test")
        splits[split] += 1
        topics[split].add(question["topic"])
        supplied_filter = question.get("filter")
        require(isinstance(supplied_filter, dict), "filter must be an object")
        require(set(supplied_filter) <= {"chapter"}, "only chapter is allowed in filter")
        if supplied_filter:
            chapter = supplied_filter["chapter"]
            require(type(chapter) is int, "chapter filter must be an integer")
            require(f"chương {chapter}" in text.casefold(), "filter chapter missing from query")
            filters[split] += 1
        alternatives = question.get("alternative_gold", [])
        require(isinstance(alternatives, list), "alternative_gold must be a list")
        for gold in [question, *alternatives]:
            require(isinstance(gold, dict), "gold must be an object")
            require(type(gold.get("gold_page")) is int, "gold_page must be an integer")
            page = lookup.get((gold.get("gold_source_id"), gold["gold_page"]))
            require(page is not None, "gold page is absent from corpus")
            evidence = gold.get("evidence_quote")
            require(isinstance(evidence, str) and bool(evidence.strip()), "empty evidence")
            require(normalized(evidence) in normalized(page["text"]), "evidence not found in gold page")
            require(all(page["metadata"].get(k) == v for k, v in supplied_filter.items()),
                    "gold evidence violates supplied filter")
            evidence_count += 1
    if len(questions) < 20 or splits["dev"] < 15 or splits["test"] < 5:
        raise ValueError("Need at least 20 questions, 15 dev and 5 test")
    if sum(filters.values()) < 3 or filters["test"] < 1:
        raise ValueError("Need at least three filtered questions, including one test")
    if topics["dev"] & topics["test"]:
        raise ValueError("Dev/test question topics overlap with the declared topic split")
    return {"split_counts": dict(splits), "filter_counts": dict(filters), "evidence_count": evidence_count}


def main() -> None:
    protocol = json.loads((ROOT / "benchmark/protocol.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    for path, expected in (
        (ROOT / protocol["questions_file"], protocol["questions_sha256"]),
        (ROOT / protocol["corpus_file"], protocol["corpus_sha256"]),
        (ROOT / manifest["source_path_or_url"], protocol["source_pdf_sha256"]),
    ):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Snapshot hash mismatch: {path.name}")
    questions = json.loads((ROOT / protocol["questions_file"]).read_text(encoding="utf-8"))
    pages = [json.loads(line) for line in
             (ROOT / protocol["corpus_file"]).read_text(encoding="utf-8").splitlines()]
    summary = validate_questions(questions, pages)
    for field in ("split_counts", "filter_counts"):
        if summary[field] != protocol[field]:
            raise ValueError(f"Counts differ from protocol: {field}")
    if {q["topic"] for q in questions if q["split"] == "test"} != set(protocol["test_topics"]):
        raise ValueError("Test topics differ from protocol")
    for position in protocol["coherence_positions"]:
        matches = [p for p in pages if p["document_id"] == position["source_id"]
                   and p["page"] == position["page"]]
        if len(matches) != 1 or not 0 <= position["character_offset"] < len(matches[0]["text"]):
            raise ValueError("Invalid coherence audit position")
    reader = PdfReader(ROOT / manifest["source_path_or_url"])
    pdf_text = {}
    for question in questions:
        for gold in [question, *question["alternative_gold"]]:
            number = gold["gold_page"]
            if number not in pdf_text:
                pdf_text[number] = normalized(reader.pages[number - 1].extract_text() or "")
            if normalized(gold["evidence_quote"]) not in pdf_text[number]:
                raise ValueError(f"{question['id']}: evidence missing from original PDF page {number}")
    print(json.dumps(summary, ensure_ascii=False))
    print("PASS: snapshot hashes, split, filters, corpus/PDF evidence and audit positions")
    print("No retrieval metrics or manual audit scores were generated.")


if __name__ == "__main__":
    main()

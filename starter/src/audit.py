"""Prepare required review samples and aggregate explicitly confirmed manual labels."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
FILES = {"coherence": "coherence_audit.csv", "metadata": "metadata_audit.csv", "grounding": "grounding_audit.csv"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def normalized(text: str) -> str:
    return " ".join(text.split())


def prepare() -> None:
    if any((RESULTS / name).exists() for name in FILES.values()):
        raise ValueError("Audit files already exist; preserve the existing review labels")
    protocol = json.loads((ROOT / "benchmark/protocol.json").read_text(encoding="utf-8"))
    selection = json.loads((RESULTS / "selection.json").read_text(encoding="utf-8"))
    test = json.loads((RESULTS / "test_summary.json").read_text(encoding="utf-8"))
    for path, expected in selection["snapshots"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen input changed: {path}")
    trace_path = ROOT / test["traces_file"]
    if hashlib.sha256(trace_path.read_bytes()).hexdigest() != test["traces_sha256"]:
        raise ValueError("Test traces differ from the recorded result")
    traces = read_jsonl(trace_path)
    pages = {(p["document_id"], p["page"]): p for p in read_jsonl(ROOT / "data/pages.jsonl")}
    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    reader = PdfReader(ROOT / manifest["source_path_or_url"])
    chapters = sorted((reader.get_destination_page_number(item) + 1, int(item.title.split()[1]))
                      for item in reader.outline if not isinstance(item, list) and item.title.startswith("Chapter "))
    pdf_text = {}
    chunks = {name: read_jsonl(RESULTS / f"chunks_{'B' if name == 'C' else name}.jsonl") for name in "ABC"}
    lookup = {name: {c["chunk_id"]: c for c in values} for name, values in chunks.items()}
    coherence, metadata, grounding = [], [], []
    for strategy in "ABC":
        for index, position in enumerate(protocol["coherence_positions"], 1):
            matches = [c for c in chunks[strategy] if c["document_id"] == position["source_id"]
                       and c["page"] == position["page"]
                       and c["metadata"]["char_start"] <= position["character_offset"] < c["metadata"]["char_end"]]
            if not matches:
                raise ValueError("No chunk covers the preselected source position")
            chunk = min(matches, key=lambda c: (c["metadata"]["char_start"], c["chunk_id"]))
            page = pages[(chunk["document_id"], chunk["page"])]
            coherence.append({
                "sample_id": f"coh-{index:02d}-{strategy}", "strategy": strategy,
                "document_id": chunk["document_id"], "source": chunk["source"], "page": chunk["page"],
                "character_offset": position["character_offset"], "chunk_id": chunk["chunk_id"],
                "chunk_text": chunk["text"], "source_page_text": page["text"],
                "proposed_score": "", "proposed_reason": "", "proposed_by": "",
                "score": "", "reason": "", "reviewer": "",
                "attribution": protocol["attribution"], "license": protocol["license"],
            })
    for trace in traces:
        hits = trace["hits"]
        grounding.append({
            "sample_id": f"grd-{trace['id']}-{trace['strategy']}", "strategy": trace["strategy"],
            "question_id": trace["id"], "question": trace["question"],
            "expected_answer": trace["expected_answer"], "gold_page": trace["gold_page"],
            "evidence_quote": trace["evidence_quote"], "filter": json.dumps(trace["filter"]),
            "top3": json.dumps([{key: hit[key] for key in ("rank", "chunk_id", "source", "page", "text")} for hit in hits], ensure_ascii=False),
            "proposed_score": "", "proposed_reason": "", "proposed_by": "",
            "score": "", "reason": "", "reviewer": "",
            "attribution": protocol["attribution"], "license": protocol["license"],
        })
        for hit in hits:
            chunk = lookup[trace["strategy"]][hit["chunk_id"]]
            page = chunk["page"]
            if page not in pdf_text:
                pdf_text[page] = reader.pages[page - 1].extract_text() or ""
            chapter = next(number for start, number in reversed(chapters) if start <= page)
            expected = {"document_id": chunk["document_id"], "source": manifest["source_path_or_url"], "page": page, "chapter": chapter}
            actual = {"document_id": hit["document_id"], "source": hit["source"], "page": hit["page"], "chapter": hit["metadata"].get("chapter")}
            metadata.append({
                "sample_id": f"meta-{trace['id']}-{trace['strategy']}-{hit['rank']}",
                "strategy": trace["strategy"], "question_id": trace["id"], "rank": hit["rank"],
                "chunk_id": hit["chunk_id"], **actual,
                "expected_document_id": expected["document_id"], "expected_source": expected["source"], "expected_page": page, "expected_chapter": chapter,
                "chunk_text": hit["text"], "source_page_text": pdf_text[page],
                "requested_chapter": trace["filter"].get("chapter", ""),
                "auto_fields_match": actual == expected,
                "auto_text_found_in_pdf": normalized(hit["text"]) in normalized(pdf_text[page]),
                "proposed_metadata_ok": "", "proposed_reason": "", "proposed_by": "",
                "metadata_ok": "", "reason": "", "reviewer": "",
                "attribution": protocol["attribution"], "license": protocol["license"],
            })
    for kind, rows, count in (("coherence", coherence, 30), ("metadata", metadata, 45), ("grounding", grounding, 15)):
        if len(rows) != count:
            raise ValueError(f"Unexpected {kind} sample count")
        write_csv(RESULTS / FILES[kind], rows)
    print("Prepared 30 coherence, 45 metadata, 15 grounding review rows. Manual labels are empty.")


def summarize_rows(rows: list[dict], score_field: str, allowed: set[str]) -> dict:
    scores = []
    for row in rows:
        score = row[score_field].strip()
        if score:
            if score not in allowed or not row["reason"].strip() or not row["reviewer"].strip():
                raise ValueError(f"{row['sample_id']}: label requires valid score, reason and reviewer")
            scores.append(int(score))
    complete = len(scores) == len(rows)
    return {"reviewed": len(scores), "total": len(rows), "complete": complete,
            "mean": sum(scores) / len(scores) if complete and scores else None,
            "counts": dict(Counter(scores)) if complete else None}


def summarize() -> None:
    data = {}
    for kind, name in FILES.items():
        with (RESULTS / name).open(encoding="utf-8-sig", newline="") as stream:
            data[kind] = list(csv.DictReader(stream))
    report = {}
    for strategy in "ABC":
        report[strategy] = {}
        for kind in FILES:
            rows = [row for row in data[kind] if row["strategy"] == strategy]
            expected = {"coherence": 10, "metadata": 15, "grounding": 5}[kind]
            if len(rows) != expected or len({row["sample_id"] for row in rows}) != expected:
                raise ValueError(f"{strategy}/{kind}: missing or duplicate review samples")
            report[strategy][kind] = summarize_rows(
                rows, "metadata_ok" if kind == "metadata" else "score",
                {"0", "1"} if kind == "metadata" else {"0", "1", "2"},
            )
        filtered = {}
        for row in data["metadata"]:
            if row["strategy"] == strategy and row["requested_chapter"]:
                filtered.setdefault(row["question_id"], []).append(row)
        complete = report[strategy]["metadata"]["complete"]
        if any(len(rows) != 3 for rows in filtered.values()):
            raise ValueError("Filter audit requires all three retrieved records per question")
        passed = sum(all(row["metadata_ok"].strip() == "1" and
                         row["chapter"] == row["requested_chapter"] for row in rows)
                     for rows in filtered.values()) if complete else None
        report[strategy]["filter_compliance"] = {
            "passed": passed, "total": len(filtered),
            "value": passed / len(filtered) if complete and filtered else None,
            "complete": complete,
        }
    output = {"status": "complete" if all(v["complete"] for s in report.values() for v in s.values()) else "pending_manual_review",
              "strategies": report,
              "note": "Only explicit score/metadata_ok with reason and reviewer counts as reviewed. Proposed AI labels and automatic matches never become manual labels automatically."}
    (RESULTS / "manual_audit_summary.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("prepare", "summarize"), default="summarize")
    args = parser.parse_args()
    prepare() if args.stage == "prepare" else summarize()


if __name__ == "__main__":
    main()

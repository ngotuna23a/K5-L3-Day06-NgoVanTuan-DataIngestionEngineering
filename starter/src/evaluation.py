"""Automatic evidence matching; human grounding/coherence labels stay separate."""
import unicodedata
from typing import Any


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """A hit requires a gold document/page and its full evidence in one chunk."""
    golds = [question, *question.get("alternative_gold", [])]
    for gold in golds:
        if not isinstance(gold.get("evidence_quote"), str) or not gold["evidence_quote"].strip():
            raise ValueError("Gold evidence must not be empty")
    labeled = []
    for rank, hit in enumerate(hits[:3], 1):
        candidates = [index for index, gold in enumerate(golds)
                      if hit.get("document_id") == gold["gold_source_id"]
                      and hit.get("page") == gold["gold_page"]]
        matched = [index for index in candidates
                   if _normalized(golds[index]["evidence_quote"]) in _normalized(hit["text"])]
        labeled.append({
            **hit, "rank": rank, "evidence_hit": bool(matched),
            "gold_source_page_match": bool(candidates), "matched_gold_indices": matched,
            "match_reason": "full_evidence" if matched else
                            "evidence_incomplete_in_chunk" if candidates else "different_source_or_page",
        })
    return {
        **question, "top_k": 3, "hits": labeled,
        "hit_at_1": bool(labeled and labeled[0]["evidence_hit"]),
        "evidence_hit_at_3": any(hit["evidence_hit"] for hit in labeled),
        "evaluation_method": "automatic_source_page_and_whitespace_normalized_full_evidence",
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate numerator/denominator and ratio separately for each split."""
    groups = {}
    seen = set()
    for trace in traces:
        identity = (trace["strategy"], trace["split"], trace["id"])
        if identity in seen:
            raise ValueError("Duplicate query trace within strategy/split")
        seen.add(identity)
        groups.setdefault((trace["strategy"], trace["split"]), []).append(trace)
    summary = {}
    for (strategy, split), rows in groups.items():
        count = len(rows)
        metrics = {"question_count": count}
        for name in ("hit_at_1", "evidence_hit_at_3"):
            hits = sum(bool(row[name]) for row in rows)
            metrics[name] = {"hits": hits, "total": count, "value": hits / count}
        summary.setdefault(strategy, {})[split] = metrics
    return summary


def select_strategy(summary: dict[str, Any], ingestion: dict[str, Any]) -> dict[str, Any]:
    """Apply the predeclared ranking using dev scores only."""
    candidates = []
    for strategy in ("A", "B", "C"):
        metrics = summary[strategy]["dev"]
        candidates.append({
            "strategy": strategy, "hit_at_1": metrics["hit_at_1"],
            "evidence_hit_at_3": metrics["evidence_hit_at_3"],
            "ingest_seconds": ingestion["strategies"][strategy]["ingest_seconds"],
        })
    if len({row["hit_at_1"]["total"] for row in candidates}) != 1:
        raise ValueError("Strategies must use the same dev questions")
    candidates.sort(key=lambda row: (
        -row["evidence_hit_at_3"]["value"], -row["hit_at_1"]["value"],
        row["ingest_seconds"], row["strategy"],
    ))
    return {"selected_strategy": candidates[0]["strategy"], "ranking": candidates}

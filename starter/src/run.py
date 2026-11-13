"""Ingest/verify A/B/C or evaluate a benchmark split with frozen test settings."""
import argparse
import csv
import hashlib
import json
import math
import statistics
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, select_strategy, summarize
from .models import Chunk, DocumentPage
from .store import QdrantStore


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_corpus() -> list[DocumentPage]:
    path = ROOT / "data/pages.jsonl"
    protocol = json.loads((ROOT / "benchmark/protocol.json").read_text(encoding="utf-8"))
    if fingerprint(path) != protocol["corpus_sha256"]:
        raise ValueError("Corpus differs from the frozen benchmark snapshot")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if len(rows) < 30 or len({(r["document_id"], r["page"]) for r in rows}) != len(rows):
        raise ValueError("Need at least 30 unique source pages")
    pages = []
    for row in rows:
        if not row["text"].strip() or row["char_count"] != len(row["text"]):
            raise ValueError(f"Invalid source text: {row['page_id']}")
        pages.append(DocumentPage(
            row["document_id"], row["source"], row["page"], row["text"],
            {**row["metadata"], "page_id": row["page_id"],
             "license": row["license"], "attribution": row["attribution"]},
        ))
    return pages


def make_chunks(pages: list[DocumentPage], config: dict) -> tuple[dict, dict]:
    strategies, elapsed = {}, {}
    if config["strategies"]["C"] != {"chunks_from": "B", "use_filter": True}:
        raise ValueError("C must reuse B chunks and change only filtering")
    for strategy in ("A", "B"):
        settings = config["strategies"][strategy]
        if settings["use_filter"]:
            raise ValueError("A and B must not apply metadata filtering")
        started = perf_counter()
        chunks = []
        for page in pages:
            if strategy == "A" and settings["chunking"] == "fixed":
                chunks.extend(fixed_size(page, settings["chunk_size"], settings["overlap"]))
            elif strategy == "B" and settings["chunking"] == "paragraph" and settings["overlap"] == 0:
                chunks.extend(by_paragraph(page, settings["chunk_size"]))
            else:
                raise ValueError("Unsupported chunking configuration")
        if not chunks:
            raise ValueError(f"Strategy {strategy} produced no chunks")
        strategies[strategy] = chunks
        elapsed[strategy] = perf_counter() - started
    strategies["C"] = strategies["B"]
    elapsed["C"] = elapsed["B"]
    return strategies, elapsed


def verify(store: QdrantStore, strategies: dict[str, list[Chunk]]) -> dict:
    """Check all persisted text/metadata, strategy isolation and chapter filters."""
    checks = {}
    bc_vectors = {}
    for strategy, chunks in strategies.items():
        records = store.records(strategy, with_vectors=True)
        expected = {c.chunk_id: c for c in chunks}
        if len(records) != len(expected):
            raise RuntimeError(f"{strategy}: stored count differs from expected chunks")
        for record in records:
            payload = record.payload
            chunk = expected.get(payload["chunk_id"])
            if chunk is None or any(payload[key] != value for key, value in asdict(chunk).items()):
                raise RuntimeError(f"{strategy}: persisted source/text/metadata mismatch")
        first = records[0]
        hits = store.search(strategy, first.vector)
        if not hits or not math.isclose(hits[0]["score"], 1.0, abs_tol=1e-5):
            raise RuntimeError(f"{strategy}: cosine self-match failed")
        for chapter in sorted({c.metadata["chapter"] for c in chunks}):
            hits = store.search(strategy, first.vector, filters={"chapter": chapter})
            if not hits or any(hit["metadata"]["chapter"] != chapter for hit in hits):
                raise RuntimeError(f"{strategy}: chapter filter failed")
        if store.search(strategy, first.vector, filters={"chapter": 99}):
            raise RuntimeError(f"{strategy}: nonmatching filter returned hits")
        checks[strategy] = {"stored_chunks": len(records), "metadata_verified": len(records), "filters": "passed"}
        if strategy in {"B", "C"}:
            bc_vectors[strategy] = {r.payload["chunk_id"]: r.vector for r in records}
    if bc_vectors["B"].keys() != bc_vectors["C"].keys() or any(
        len(vector) != len(bc_vectors["C"][key]) or any(
            not math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-7)
            for left, right in zip(vector, bc_vectors["C"][key], strict=True)
        ) for key, vector in bc_vectors["B"].items()
    ):
        raise RuntimeError("B and C do not contain identical chunks/vectors")
    return checks


def ingest(config: dict, pages: list[DocumentPage]) -> None:
    setup = json.loads((ROOT / "artifacts/local_setup.json").read_text(encoding="utf-8"))
    embedding = config["embedding"]
    if embedding != setup["embedding"]:
        raise ValueError("Embedding settings changed; run check_local_setup first")
    for model in setup["model_files"]:
        if fingerprint(ROOT / model["path"]) != model["sha256"]:
            raise ValueError("Model weights differ from the verified setup")
    started = perf_counter()
    embedder = MyEmbedder(
        embedding["model_name"], cache_dir=ROOT / embedding["cache_dir"],
        threads=embedding["threads"], batch_size=embedding["batch_size"],
    )
    model_load_seconds = perf_counter() - started
    strategies, chunk_seconds = make_chunks(pages, config)
    store_config = config["vector_store"]
    store = QdrantStore(ROOT / store_config["path"], embedding["dimensions"], store_config["collection"])
    summary, prepared = {}, {}
    RESULTS.mkdir(exist_ok=True)
    try:
        store.create_schema()
        for strategy, chunks in strategies.items():
            texts = [c.text for c in chunks]
            if strategy != "C":
                tokens = embedder.count_document_tokens(texts)
                if max(tokens) > embedding["max_tokens"]:
                    raise ValueError(f"{strategy}: chunk exceeds model context; reduce chunk size before embedding")
                print(f"{strategy}: embedding {len(chunks)} chunks...", flush=True)
                started = perf_counter()
                vectors = embedder.embed_documents(texts)
                embed_seconds = perf_counter() - started
                prepared[strategy] = (vectors, tokens, embed_seconds)
                with (RESULTS / f"chunks_{strategy}.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
                    for chunk in chunks:
                        stream.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
            else:
                vectors, tokens, embed_seconds = prepared["B"]
                print("C: reusing B chunks and vectors...", flush=True)
            started = perf_counter()
            changes = store.upsert(strategy, chunks, vectors)
            upsert_seconds = perf_counter() - started
            lengths = [len(text) for text in texts]
            summary[strategy] = {
                "config": config["strategies"][strategy],
                "chunks_file": f"results/chunks_{'B' if strategy == 'C' else strategy}.jsonl",
                "chunk_count": len(chunks), "total_characters": sum(lengths),
                "lengths": {"min": min(lengths), "max": max(lengths), "mean": statistics.mean(lengths),
                            "median": statistics.median(lengths),
                            "histogram": {"1-250": sum(n <= 250 for n in lengths),
                                          "251-500": sum(250 < n <= 500 for n in lengths),
                                          "501-1000": sum(500 < n <= 1000 for n in lengths),
                                          "over-1000": sum(n > 1000 for n in lengths)}},
                "input_tokens_including_prefix_and_special": sum(tokens),
                "max_input_tokens": max(tokens), "truncated_chunks": 0,
                "chunking_seconds": chunk_seconds[strategy], "embedding_seconds": embed_seconds,
                "upsert_seconds": upsert_seconds,
                "ingest_seconds": chunk_seconds[strategy] + embed_seconds + upsert_seconds,
                "preparation_reused_from": "B" if strategy == "C" else None,
                "api_cost_usd": 0, **changes,
            }
            print(f"{strategy}: stored {len(chunks)} chunks; obsolete {changes['removed_obsolete']}", flush=True)
        checks = verify(store, strategies)
    finally:
        store.close()
    output = {
        "created_at": datetime.now(timezone.utc).isoformat(), "page_count": len(pages),
        "corpus_sha256": fingerprint(ROOT / "data/pages.jsonl"),
        "embedding": embedding, "model_files": setup["model_files"],
        "packages": {name: version(name) for name in ("fastembed", "qdrant-client", "onnxruntime", "tokenizers")},
        "vector_store": store_config, "model_load_seconds": model_load_seconds,
        "strategies": summary, "verification": checks, "benchmark_run": False,
        "notes": ["Chunks stay within source pages; paragraph boundaries are heuristic because PDF text has no blank-line paragraphs.",
                  "C reuses B preparation; its chunking/embedding durations are measured B durations shared with C, not an additional embedding run. Ingest seconds sums those stages plus each strategy's upsert.",
                  "Token counts include passage prefix/special tokens before truncation; no input exceeded the model context.",
                  "Upsert replaces snapshots for documents present in the batch and removes their obsolete chunks after successful writes. Empty batches leave existing documents unchanged.",
                  "Verification uses source vectors, not benchmark queries. No dev/test retrieval metrics or human labels generated."],
    }
    (RESULTS / "ingestion_summary.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Ingest OK. B/C chunks and vectors match. Summary: results/ingestion_summary.json")


def benchmark(config: dict, pages: list[DocumentPage], split: str) -> None:
    protocol_path = ROOT / "benchmark/protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    questions_path = ROOT / protocol["questions_file"]
    ingestion_path = RESULTS / "ingestion_summary.json"
    ingestion = json.loads(ingestion_path.read_text(encoding="utf-8"))
    if fingerprint(questions_path) != protocol["questions_sha256"]:
        raise ValueError("Questions differ from the frozen benchmark")
    if config["embedding"] != ingestion["embedding"] or config["vector_store"] != ingestion["vector_store"]:
        raise ValueError("Embedding/store settings differ from the ingested corpus")
    if any(config["strategies"][name] != ingestion["strategies"][name]["config"] for name in ("A", "B", "C")):
        raise ValueError("Strategy settings changed; ingest again before evaluation")
    if any(version(name) != value for name, value in ingestion["packages"].items()):
        raise ValueError("Runtime packages differ from the ingested model setup")
    for model in ingestion["model_files"]:
        if fingerprint(ROOT / model["path"]) != model["sha256"]:
            raise ValueError("Model weights changed after ingestion")
    snapshot_paths = ["starter/config.json", "benchmark/protocol.json", protocol["questions_file"],
                      protocol["corpus_file"], "results/ingestion_summary.json",
                      *[f"starter/src/{name}.py" for name in ("chunking", "embeddings", "store", "evaluation", "run")]]
    snapshots = {path: fingerprint(ROOT / path) for path in snapshot_paths}
    selection_path = RESULTS / "selection.json"
    if (RESULTS / "test_summary.json").exists():
        raise ValueError("Test has already been evaluated; keep its results and do not tune from test")
    if split == "test":
        if not selection_path.exists():
            raise ValueError("Run dev and freeze selection before evaluating test")
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        if selection["snapshots"] != snapshots:
            raise ValueError("Inputs/code differ from dev selection; freeze on dev before test")
    questions = [q for q in json.loads(questions_path.read_text(encoding="utf-8")) if q["split"] == split]
    if len(questions) != protocol["split_counts"][split] or len({q["id"] for q in questions}) != len(questions):
        raise ValueError("Benchmark split count/IDs differ from protocol")
    # Retrieval inputs are deliberately projected before embedding/search; gold stays in evaluation.
    inputs = [{key: q[key] for key in protocol["retrieval_input_fields"]} for q in questions]
    embedding = config["embedding"]
    started = perf_counter()
    embedder = MyEmbedder(embedding["model_name"], cache_dir=ROOT / embedding["cache_dir"],
                          threads=embedding["threads"], batch_size=embedding["batch_size"])
    queries = {item["id"]: embedder.embed_query(item["question"]) for item in inputs}
    strategies, _ = make_chunks(pages, config)
    settings = config["vector_store"]
    store = QdrantStore(ROOT / settings["path"], embedding["dimensions"], settings["collection"])
    traces = []
    try:
        verify(store, strategies)
        for strategy in ("A", "B", "C"):
            for item, gold in zip(inputs, questions, strict=True):
                filters = item["filter"] if config["strategies"][strategy]["use_filter"] else {}
                search_started = perf_counter()
                hits = store.search(strategy, queries[item["id"]], top_k=3, filters=filters)
                seconds = perf_counter() - search_started
                trace = evaluate_query(gold, hits)
                traces.append({**trace, "strategy": strategy, "applied_filter": filters,
                               "search_seconds": seconds, "attribution": protocol["attribution"],
                               "license": protocol["license"]})
    finally:
        store.close()
    metrics = summarize(traces)
    trace_path = RESULTS / f"{split}_traces.jsonl"
    with trace_path.open("w", encoding="utf-8", newline="\n") as stream:
        for trace in traces:
            stream.write(json.dumps(trace, ensure_ascii=False) + "\n")
    output = {
        "created_at": datetime.now(timezone.utc).isoformat(), "split": split,
        "query_embedding_count": len(queries), "retrieval_query_count": len(traces),
        "elapsed_seconds": perf_counter() - started, "metrics": metrics,
        "traces_file": trace_path.relative_to(ROOT).as_posix(), "traces_sha256": fingerprint(trace_path),
        "snapshots": snapshots,
        "evaluation_method": "automatic full evidence substring after Unicode/whitespace normalization; matching source/page required",
        "limitations": "Exact evidence is an automatic proxy. Equivalent evidence needs documented adjudication; human grounding/coherence/metadata labels are not inferred.",
        "api_cost_usd": 0, "test_evaluated": split == "test",
    }
    if split == "dev":
        selection = {**select_strategy(metrics, ingestion), "frozen_at": output["created_at"],
                     "selection_split": "dev", "selection_rule": protocol["selection_rule"],
                     "snapshots": snapshots, "dev_traces_sha256": output["traces_sha256"],
                     "test_evaluated": False}
        selection_path.write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output["selected_strategy"] = selection["selected_strategy"]
    else:
        output["selected_strategy"] = selection["selected_strategy"]
    (RESULTS / f"{split}_summary.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log_path = ROOT / "artifacts/experiment_log.csv"
    with log_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    for row in rows:
        values = metrics[row["strategy"]][split]
        for column, metric in (("hit1", "hit_at_1"), ("hit3", "evidence_hit_at_3")):
            value = values[metric]
            row[f"{split}_{column}"] = f"{value['hits']}/{value['total']}"
        if row["notes"] in {"Before retrieval; metrics not yet measured", "Dev retrieval completed; test not run"}:
            row["notes"] = "Dev retrieval completed; test not run" if split == "dev" else "Dev and test retrieval completed"
    with log_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    for strategy in ("A", "B", "C"):
        values = metrics[strategy][split]
        first, top3 = values["hit_at_1"], values["evidence_hit_at_3"]
        print(f"{strategy} {split}: Hit@1 {first['hits']}/{first['total']} | Evidence Hit@3 {top3['hits']}/{top3['total']}")
    if split == "dev":
        print(f"Selected on dev: {selection['selected_strategy']}. Frozen settings: results/selection.json")
    print(f"Benchmark {split} OK. Traces: {trace_path.relative_to(ROOT).as_posix()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("ingest", "verify", "benchmark"), default="ingest")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    args = parser.parse_args()
    config = json.loads((ROOT / "starter/config.json").read_text(encoding="utf-8"))
    store_config = config["vector_store"]
    if (store_config["backend"], store_config["distance"], store_config["search_mode"]) != ("qdrant-local", "cosine", "exact"):
        raise ValueError("Only Qdrant Local exact cosine is configured")
    pages = load_corpus()
    if args.stage == "ingest":
        ingest(config, pages)
    elif args.stage == "benchmark":
        benchmark(config, pages, args.split)
    else:
        strategies, _ = make_chunks(pages, config)
        store = QdrantStore(ROOT / store_config["path"], config["embedding"]["dimensions"], store_config["collection"])
        try:
            checks = verify(store, strategies)
        finally:
            store.close()
        print(json.dumps(checks, ensure_ascii=False))
        print("Verify OK. Persisted chunks, metadata, filters and B/C vectors match.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        RESULTS.mkdir(exist_ok=True)
        with (RESULTS / "ingestion_errors.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "error_type": type(error).__name__, "message": str(error),
                "traceback": traceback.format_exc(),
            }, ensure_ascii=False) + "\n")
        raise

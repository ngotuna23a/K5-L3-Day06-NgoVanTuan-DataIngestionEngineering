"""Smoke-test real embeddings and persistent Qdrant independently of benchmark."""
import argparse
import hashlib
import json
import math
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter

from .embeddings import MyEmbedder


ROOT = Path(__file__).resolve().parents[2]


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-model", action="store_true", help="Allow initial model download")
    args = parser.parse_args()
    packages = {}
    for name in ("pypdf", "fastembed", "qdrant-client", "onnxruntime", "numpy", "tokenizers"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            sys.exit(f"Missing dependency: {name}. Install starter/requirements-local.txt first.")
    from qdrant_client import QdrantClient, models

    config = json.loads((ROOT / "starter/config.json").read_text(encoding="utf-8"))
    embedding = config["embedding"]
    expected = {
        "model_file": "onnx/model.onnx", "pooling": "mean", "normalize": True,
        "query_prefix": "query: ", "document_prefix": "passage: ", "max_tokens": 512,
    }
    if any(embedding.get(key) != value for key, value in expected.items()):
        raise ValueError("Embedding configuration differs from the E5 adapter implementation")
    started = perf_counter()
    embedder = MyEmbedder(
        embedding["model_name"], cache_dir=ROOT / embedding["cache_dir"],
        threads=embedding["threads"], batch_size=embedding["batch_size"],
        local_files_only=not args.download_model,
    )
    if embedder.dimensions != embedding["dimensions"]:
        raise RuntimeError("Configured vector dimensions differ from embedder")
    documents = ["A red apple grows on a tree.", "A blue boat travels along a river."]
    vectors = embedder.embed_documents(documents)
    query = embedder.embed_query("Con thuyền di chuyển ở đâu?")
    if vectors[0] == vectors[1] or len(query) != embedder.dimensions:
        raise RuntimeError("Smoke vectors are invalid or indistinguishable")
    cache_root = ROOT / ".cache"
    cache_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qdrant_smoke_", dir=cache_root) as directory:
        client = QdrantClient(path=directory)
        try:
            client.create_collection("smoke", vectors_config=models.VectorParams(
                size=embedder.dimensions, distance=models.Distance.COSINE
            ))
            points = [models.PointStruct(id=n, vector=vector, payload={
                "chapter": n, "source": "smoke-test", "page": n, "text": text,
            }) for n, (text, vector) in enumerate(zip(documents, vectors, strict=True), 1)]
            for _ in range(2):
                client.upsert("smoke", points=points, wait=True)
            if client.count("smoke", exact=True).count != 2:
                raise RuntimeError("Repeated upsert duplicated points")
        finally:
            client.close()
        client = QdrantClient(path=directory)
        try:
            if client.count("smoke", exact=True).count != 2:
                raise RuntimeError("Points were not persisted across reopen")
            unfiltered = client.query_points(
                "smoke", query=vectors[0], limit=2,
            ).points
            if len(unfiltered) != 2 or unfiltered[0].id != 1 or not math.isclose(unfiltered[0].score, 1.0, abs_tol=1e-5):
                raise RuntimeError("Cosine self-match did not rank the original vector first")
            hits = client.query_points(
                "smoke", query=query, limit=3,
                query_filter=models.Filter(must=[models.FieldCondition(
                    key="chapter", match=models.MatchValue(value=2)
                )]), with_payload=True,
            ).points
            if len(hits) != 1 or hits[0].payload["chapter"] != 2 or not math.isfinite(hits[0].score):
                raise RuntimeError("Metadata filter/vector search failed")
            missing = client.query_points(
                "smoke", query=query, limit=3,
                query_filter=models.Filter(must=[models.FieldCondition(
                    key="chapter", match=models.MatchValue(value=99)
                )]),
            ).points
            if missing:
                raise RuntimeError("Nonmatching filter returned points")
        finally:
            client.close()
    cache_dir = ROOT / embedding["cache_dir"]
    store_config = config["vector_store"]
    client = QdrantClient(path=str(ROOT / store_config["path"]))
    try:
        collection = store_config["collection"]
        if not client.collection_exists(collection):
            client.create_collection(collection, vectors_config=models.VectorParams(
                size=embedder.dimensions, distance=models.Distance.COSINE
            ))
        schema = client.get_collection(collection).config.params.vectors
        if not isinstance(schema, models.VectorParams) or schema.size != embedder.dimensions or schema.distance != models.Distance.COSINE:
            raise RuntimeError("Existing collection differs from the configured vector schema")
        collection_points = client.count(collection, exact=True).count
    finally:
        client.close()
    report = {
        "python": sys.version.split()[0], "packages": packages,
        "embedding": embedding, "vector_store": config["vector_store"],
        "model_files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": fingerprint(p)}
                        for p in sorted(cache_dir.rglob("*.onnx"))],
        "checks": ["real document/query vectors", "384 dimensions and finite L2 vectors",
                   "repeated upsert without duplicates", "persistent storage after reopen",
                   "cosine vector search", "chapter filter", "nonmatching filter returns no hits"],
        "smoke_elapsed_seconds": round(perf_counter() - started, 3),
        "api_cost_usd": 0,
        "collection_points": collection_points,
        "benchmark_run": False,
        "note": "Smoke test uses two artificial sentences, not benchmark questions. No retrieval metrics or manual labels generated.",
    }
    output = ROOT / "artifacts/local_setup.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS: real 384-dimensional document/query embeddings")
    print("PASS: Qdrant persistence, cosine search, filters and repeat upsert")
    print(f"Collection ready: {collection} | points: {collection_points}")
    print("Local setup OK. Report: artifacts/local_setup.json")


if __name__ == "__main__":
    main()

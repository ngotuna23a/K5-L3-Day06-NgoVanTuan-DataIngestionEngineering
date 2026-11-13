"""Persistent Qdrant Local storage, exact cosine search and chapter filtering."""
import json
import math
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from .models import Chunk


class QdrantStore:
    def __init__(self, path: Path, dimensions: int, collection: str = "day06_python") -> None:
        if type(dimensions) is not int or dimensions < 1:
            raise ValueError("dimensions must be a positive integer")
        self.dimensions = dimensions
        self.collection = collection
        self.client = QdrantClient(path=str(path))

    def close(self) -> None:
        self.client.close()

    def create_schema(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(self.collection, vectors_config=models.VectorParams(
                size=self.dimensions, distance=models.Distance.COSINE
            ))
        schema = self.client.get_collection(self.collection).config.params.vectors
        if not isinstance(schema, models.VectorParams) or schema.size != self.dimensions or schema.distance != models.Distance.COSINE:
            raise ValueError("Existing collection has a different vector schema")

    def _vector(self, vector: list[float]) -> None:
        if len(vector) != self.dimensions or not all(math.isfinite(v) for v in vector):
            raise ValueError("Vector dimensions/values are invalid")
        if not any(vector):
            raise ValueError("Cosine search requires nonzero vectors")

    @staticmethod
    def _filter(strategy: str, filters: dict[str, Any] | None = None) -> models.Filter:
        if strategy not in {"A", "B", "C"}:
            raise ValueError("strategy must be A, B or C")
        filters = filters or {}
        if set(filters) - {"chapter"}:
            raise ValueError("Only chapter filtering is supported")
        conditions = [models.FieldCondition(key="strategy", match=models.MatchValue(value=strategy))]
        for key, value in filters.items():
            if type(value) is not int:
                raise ValueError("chapter must be an integer")
            conditions.append(models.FieldCondition(key=f"metadata.{key}", match=models.MatchValue(value=value)))
        return models.Filter(must=conditions)

    def records(self, strategy: str, *, with_vectors: bool = False) -> list[Any]:
        records, offset = [], None
        while True:
            batch, offset = self.client.scroll(
                self.collection, scroll_filter=self._filter(strategy), limit=256,
                offset=offset, with_payload=True, with_vectors=with_vectors,
            )
            records.extend(batch)
            if offset is None:
                return records

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> dict[str, int]:
        """Replace complete snapshots of the documents supplied for one strategy.

        Validate the whole batch before writing. Remove obsolete chunks only for
        those documents, after new points have been written successfully.
        """
        self._filter(strategy)
        if len(chunks) != len(vectors) or len({c.chunk_id for c in chunks}) != len(chunks):
            raise ValueError("Chunk/vector lengths differ or chunk IDs are duplicated")
        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._vector(vector)
            if not chunk.text.strip() or not chunk.document_id or not chunk.source or chunk.page < 1:
                raise ValueError("Chunks require text, document ID, source and a positive page")
            if type(chunk.metadata.get("chapter")) is not int:
                raise ValueError("Chunks require verified integer chapter metadata")
            json.dumps(chunk.metadata, allow_nan=False)
            points.append(models.PointStruct(
                id=str(uuid5(NAMESPACE_URL, f"{strategy}:{chunk.chunk_id}")), vector=vector,
                payload={"strategy": strategy, "chunk_id": chunk.chunk_id,
                         "document_id": chunk.document_id, "source": chunk.source,
                         "page": chunk.page, "text": chunk.text, "metadata": chunk.metadata},
            ))
        documents = {c.document_id for c in chunks}
        incoming = {str(point.id) for point in points}
        obsolete = [record.id for record in self.records(strategy)
                    if record.payload["document_id"] in documents and str(record.id) not in incoming]
        for start in range(0, len(points), 128):
            self.client.upsert(self.collection, points=points[start:start + 128], wait=True)
        if obsolete:
            self.client.delete(self.collection, points_selector=models.PointIdsList(points=obsolete), wait=True)
        return {"upserted": len(points), "removed_obsolete": len(obsolete)}

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Qdrant Local uses exact cosine search; filter values are typed payloads."""
        self._vector(query_vector)
        if type(top_k) is not int or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        hits = self.client.query_points(
            self.collection, query=query_vector, limit=top_k,
            query_filter=self._filter(strategy, filters), with_payload=True,
        ).points
        return [{"chunk_id": hit.payload["chunk_id"], "text": hit.payload["text"], "score": hit.score,
                 "document_id": hit.payload["document_id"], "source": hit.payload["source"],
                 "page": hit.payload["page"], "metadata": hit.payload["metadata"]} for hit in hits]

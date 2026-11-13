"""Real Qdrant tests with small basis vectors; no embedding/benchmark scores."""
import tempfile
import unittest
from pathlib import Path

from starter.src.models import Chunk
from starter.src.store import QdrantStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="qdrant_store_test_")
        self.store = QdrantStore(Path(self.directory.name), 3)
        self.store.create_schema()

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def chunk(self, identifier, document="doc1", chapter=1):
        return Chunk(identifier, document, "source.pdf", 17, identifier, {"chapter": chapter})

    def test_repeat_upsert_and_persistence(self):
        chunk = self.chunk("first")
        for _ in range(2):
            self.store.upsert("A", [chunk], [[1.0, 0.0, 0.0]])
        self.store.close()
        self.store = QdrantStore(Path(self.directory.name), 3)
        self.assertEqual(len(self.store.records("A")), 1)
        hits = self.store.search("A", [1.0, 0.0, 0.0])
        self.assertEqual(hits[0]["chunk_id"], "first")
        self.assertAlmostEqual(hits[0]["score"], 1.0)

    def test_stale_chunks_removed_only_for_target_documents_and_strategy(self):
        chunks = [self.chunk("old1"), self.chunk("old2"), self.chunk("keep", "doc2")]
        self.store.upsert("A", chunks, [[1.0, 0.0, 0.0]] * 3)
        self.store.upsert("C", [chunks[0]], [[1.0, 0.0, 0.0]])
        changes = self.store.upsert("A", [self.chunk("new")], [[0.0, 1.0, 0.0]])
        self.assertEqual(changes["removed_obsolete"], 2)
        self.assertEqual({r.payload["chunk_id"] for r in self.store.records("A")}, {"new", "keep"})
        self.assertEqual(len(self.store.records("C")), 1)

    def test_strategy_and_chapter_filters(self):
        self.store.upsert("A", [self.chunk("one"), self.chunk("two", chapter=2)],
                          [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        self.store.upsert("B", [self.chunk("other", chapter=2)], [[1.0, 0.0, 0.0]])
        hits = self.store.search("A", [1.0, 0.0, 0.0], filters={"chapter": 2})
        self.assertEqual([hit["chunk_id"] for hit in hits], ["two"])
        self.assertEqual(self.store.search("A", [1.0, 0.0, 0.0], filters={"chapter": 99}), [])
        for filters in [{"source": "gold.pdf"}, {"chapter": True}]:
            with self.assertRaises(ValueError):
                self.store.search("A", [1.0, 0.0, 0.0], filters=filters)

    def test_invalid_batch_does_not_write_partial_points(self):
        for vectors in [[[1.0, 0.0, 0.0], [1.0]], [[1.0, 0.0, 0.0]],
                        [[1.0, 0.0, 0.0], [float("nan"), 0.0, 1.0]]]:
            with self.assertRaises(ValueError):
                self.store.upsert("A", [self.chunk("one"), self.chunk("two")], vectors)
            self.assertEqual(self.store.records("A"), [])

    def test_schema_mismatch_is_reported(self):
        self.store.dimensions = 2
        with self.assertRaises(ValueError):
            self.store.create_schema()


if __name__ == "__main__":
    unittest.main()

"""Adapter unit tests only; actual vectors are checked by check_local_setup."""
import unittest

from starter.src.embeddings import MyEmbedder


class Vector:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class RecordingBackend:
    def __init__(self, values=None):
        self.values = values if values is not None else [1.0] + [0.0] * 383
        self.inputs = []

    def embed(self, texts, **kwargs):
        self.inputs.extend(texts)
        return [Vector(self.values) for _ in texts]


class EmbeddingAdapterTests(unittest.TestCase):
    def adapter(self, backend=None):
        adapter = object.__new__(MyEmbedder)
        adapter.dimensions = 384
        adapter.batch_size = 8
        adapter._model = backend or RecordingBackend()
        return adapter

    def test_prefixes_are_distinct_for_query_and_document(self):
        adapter = self.adapter()
        self.assertEqual(len(adapter.embed_documents(["Example"])[0]), 384)
        self.assertEqual(len(adapter.embed_query("Example")), 384)
        self.assertEqual(adapter._model.inputs, ["passage: Example", "query: Example"])

    def test_empty_batch_does_not_call_backend(self):
        adapter = self.adapter()
        self.assertEqual(adapter.embed_documents([]), [])
        self.assertEqual(adapter._model.inputs, [])

    def test_blank_inputs_are_rejected(self):
        for text in ("", "  ", None):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.adapter().embed_query(text)

    def test_wrong_dimensions_are_rejected(self):
        with self.assertRaises(RuntimeError):
            self.adapter(RecordingBackend([1.0, 0.0])).embed_query("Example")

    def test_nonfinite_values_are_rejected(self):
        with self.assertRaises(RuntimeError):
            self.adapter(RecordingBackend([float("nan")] * 384)).embed_query("Example")

    def test_nonunit_vector_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.adapter(RecordingBackend([0.0] * 384)).embed_query("Example")

    def test_other_models_are_not_silently_substituted(self):
        with self.assertRaises(ValueError):
            MyEmbedder("unsupported-model")


if __name__ == "__main__":
    unittest.main()

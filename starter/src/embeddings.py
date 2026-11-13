"""Real multilingual E5 embeddings using local FastEmbed/ONNX CPU inference."""
import math
from pathlib import Path
from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Use E5 mean pooling, L2 normalization and explicit retrieval prefixes."""

    def __init__(
        self, model_name: str = "intfloat/multilingual-e5-small", *,
        cache_dir: Path | None = None, threads: int = 2, batch_size: int = 8,
        local_files_only: bool = True,
    ) -> None:
        if model_name != "intfloat/multilingual-e5-small":
            raise ValueError("This adapter supports only intfloat/multilingual-e5-small")
        if threads < 1 or batch_size < 1:
            raise ValueError("threads and batch_size must be positive")
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType

        if not any(m["model"].lower() == model_name.lower() for m in TextEmbedding.list_supported_models()):
            TextEmbedding.add_custom_model(
                model=model_name, pooling=PoolingType.MEAN, normalization=True,
                sources=ModelSource(hf=model_name), dim=384,
                model_file="onnx/model.onnx", license="mit", size_in_gb=0.47,
            )
        self.model_name = model_name
        self.dimensions = 384
        self.batch_size = batch_size
        cache_dir = cache_dir or Path(__file__).resolve().parents[2] / ".cache/fastembed"
        self._model = TextEmbedding(
            model_name=model_name, cache_dir=str(cache_dir), threads=threads,
            providers=["CPUExecutionProvider"], local_files_only=local_files_only,
        )

    def _embed(self, texts: list[str], prefix: str) -> list[list[float]]:
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding inputs must be nonempty strings")
        if not texts:
            return []
        vectors = [vector.tolist() for vector in self._model.embed(
            [prefix + text for text in texts], batch_size=self.batch_size
        )]
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding provider returned the wrong number of vectors")
        for vector in vectors:
            if len(vector) != self.dimensions or not all(math.isfinite(value) for value in vector):
                raise RuntimeError("Embedding vector has invalid dimensions or values")
            norm = math.sqrt(sum(value * value for value in vector))
            if not math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4):
                raise RuntimeError("Embedding vector is not L2 normalized")
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "passage: ")

    def embed_query(self, question: str) -> list[float]:
        return self._embed([question], "query: ")[0]

    def count_document_tokens(self, texts: list[str]) -> list[int]:
        """Count untruncated passage inputs, including prefix and special tokens."""
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_str(self._model.model.tokenizer.to_str())
        tokenizer.no_padding()
        tokenizer.no_truncation()
        return [len(encoded.ids) for encoded in tokenizer.encode_batch(
            ["passage: " + text for text in texts]
        )]

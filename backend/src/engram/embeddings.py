"""Local text embeddings (ONNX via fastembed), used by the worker for chunks and by the API
for questions. The model downloads once (about 70 MB) and then runs in-process."""

from collections.abc import Sequence
from functools import lru_cache

from fastembed import TextEmbedding

DIMENSION = 384  # fixed in the schema: chunks.embedding is vector(384)


class Embedder:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = TextEmbedding(model_name)
        if self._model.embedding_size != DIMENSION:
            raise ValueError(
                f"{model_name} has {self._model.embedding_size} dimensions; the schema expects"
                f" {DIMENSION}. Changing models needs a migration and a re-embed."
            )

    def passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.passage_embed(list(texts))]

    def query(self, text: str) -> list[float]:
        vector: list[float] = next(iter(self._model.query_embed(text))).tolist()
        return vector


@lru_cache
def get_embedder(model_name: str) -> Embedder:
    return Embedder(model_name)

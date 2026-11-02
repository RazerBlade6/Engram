"""Local text embeddings (ONNX via fastembed), used by the worker for chunks and by the API
for questions. The model downloads once (about 70 MB) and then runs in-process."""

import threading
from collections.abc import Sequence

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


_loaded: dict[str, Embedder] = {}
_lock = threading.Lock()


def get_embedder(model_name: str) -> Embedder:
    """The model, loaded once per process. Thread-safe: the API starts loading it at startup,
    and a question that arrives meanwhile waits for that load instead of starting another."""
    with _lock:
        if model_name not in _loaded:
            _loaded[model_name] = Embedder(model_name)
        return _loaded[model_name]

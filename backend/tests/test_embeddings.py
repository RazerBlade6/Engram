import math
import time

import pytest

from engram.embeddings import DIMENSION, get_embedder


def test_embedder_ranks_related_text_higher() -> None:
    embedder = get_embedder("BAAI/bge-small-en-v1.5")
    question = embedder.query("Which organelle makes ATP?")
    related, unrelated = embedder.passages(
        [
            "Mitochondria produce ATP through cellular respiration.",
            "The French Revolution began in 1789.",
        ]
    )
    assert len(question) == DIMENSION

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        return dot / (math.hypot(*a) * math.hypot(*b))

    assert cosine(question, related) > cosine(question, unrelated) + 0.1


def test_concurrent_loads_share_one_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API starts loading the model at startup; a question arriving meanwhile waits for
    that load rather than starting a second one."""
    from concurrent.futures import ThreadPoolExecutor

    from engram import embeddings

    made: list[str] = []

    class Slow:
        def __init__(self, name: str) -> None:
            time.sleep(0.05)
            made.append(name)

    monkeypatch.setattr(embeddings, "_loaded", {})
    monkeypatch.setattr(embeddings, "Embedder", Slow)
    with ThreadPoolExecutor(4) as pool:
        got = list(pool.map(embeddings.get_embedder, ["m"] * 4))
    assert made == ["m"]
    assert all(g is got[0] for g in got)

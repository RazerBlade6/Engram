import math

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

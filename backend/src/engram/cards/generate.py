"""Generates a chapter's cards from its passages, and keeps only the ones its sources support.

Cards are strictly grounded (D2): each must cite at least one passage and quote the words in
it that support the card. A card whose quotes can't be found in the passages it cites is
dropped rather than kept on trust, because a wrong card is worse than none.
"""

import random
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

PROMPT_VERSION = "cards-v2"

# Passages are sent in batches of about this many words, a few subsections at a time, so a
# long chapter becomes several calls that run side by side.
BATCH_WORDS = 2500
MAX_TOKENS = 12000

SYSTEM = """You write flashcards for university students from their course materials. The \
student has just covered this chapter in class and will review your cards with spaced \
repetition, so every card must be correct and worth remembering.

Use only the passages you are given. Never add facts from general knowledge, even true ones. \
If a passage is thin or is only an example, exercise or review question, make no card from it.

Make one card for each idea a student should be able to recall in an exam: key terms and \
their definitions, mechanisms and causes, distinctions between related ideas, the findings \
that matter, and what figures and tables show. Skip trivia, learning objectives, review and \
discussion questions, and names or dates that the passage does not treat as important. \
Never make two cards that test the same fact.

Card kinds:
- basic: a question and a short answer. The question must make sense on its own, without \
the passage, and have one clear answer. Keep answers to one or two sentences.
- cloze: one sentence taken or closely adapted from the passage, with the key term or \
phrase hidden by wrapping it in double braces, like "The {{hippocampus}} consolidates new \
memories." Hide exactly one span, and only a part worth recalling. The answer is the hidden \
text, exactly.
- mcq: a question, its correct answer, and three distractors. Distractors are related ideas \
from the same material that a student could confuse with the answer, are clearly wrong, and \
are similar to the answer in length and form. Never use "all of the above" or "none of the \
above".

Mix the kinds: definitions usually suit cloze or basic; choosing between related ideas suits \
mcq.

For each card, cite the passages it comes from by number and quote, word for word, the \
sentence or phrase in each passage that supports it. Write plainly; do not refer to "the \
passage" or "the text" in the card itself."""


class Source(BaseModel):
    passage: int = Field(description="The number of a passage, as in [P3].")
    quote: str = Field(description="The words in that passage that support the card, verbatim.")


class GeneratedCard(BaseModel):
    kind: Literal["basic", "cloze", "mcq"]
    concept: str = Field(description="The idea the card tests, in two to five words.")
    prompt: str = Field(description="The question, or for cloze the sentence with {{braces}}.")
    answer: str
    distractors: list[str] = Field(description="mcq: three wrong choices. Otherwise empty.")
    sources: list[Source]


class CardSet(BaseModel):
    cards: list[GeneratedCard]


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    group: str
    kind: str
    heading_path: list[str]
    content: str
    locations: list[dict[str, Any]]

    @property
    def words(self) -> int:
        return len(self.content.split())


@dataclass(frozen=True)
class Card:
    kind: str
    concept: str
    prompt: str
    answer: str
    choices: list[str]
    sources: list[dict[str, Any]]


def batches(passages: list[Passage], budget: int = BATCH_WORDS) -> list[list[Passage]]:
    """Consecutive passages in batches of about `budget` words. A subsection (`group`) stays in
    one batch unless it is larger than the budget on its own."""
    groups: list[list[Passage]] = []
    for p in passages:
        if groups and groups[-1][0].group == p.group:
            groups[-1].append(p)
        else:
            groups.append([p])

    out: list[list[Passage]] = []
    current: list[Passage] = []
    size = 0
    for group in groups:
        group_size = sum(p.words for p in group)
        if current and size + group_size > budget:
            out.append(current)
            current, size = [], 0
        for p in group:
            if current and size + p.words > budget:
                out.append(current)
                current, size = [], 0
            current.append(p)
            size += p.words
    if current:
        out.append(current)
    return out


# At most one card for about this many words of passage. Without a cap a 30-page chapter
# became 150 cards, many of them trivia: more than a student will keep up with.
WORDS_PER_CARD = 150


def card_limit(batch: list[Passage]) -> int:
    return max(2, sum(p.words for p in batch) // WORDS_PER_CARD)


def prompt_for(chapter: str, batch: list[Passage]) -> str:
    parts = [
        f"Chapter: {chapter}",
        f"Make at most {card_limit(batch)} cards, for the ideas that matter most. Fewer is"
        " fine when the passages have less worth remembering.",
    ]
    for i, p in enumerate(batch, 1):
        label = {"figure": "figure", "table": "table"}.get(p.kind, "text")
        heading = " > ".join(p.heading_path) or chapter
        parts.append(f"[P{i}] ({label}; {heading})\n{p.content}")
    return "\n\n".join(parts)


def _normal(text: str) -> str:
    """Lowercase letters and digits only, so a quote matches despite changes in spacing,
    punctuation, quote marks, hyphenation or a dropped heading prefix."""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^a-z0-9]+", "", text)


_CLOZE = re.compile(r"\{\{(.+?)\}\}")


def accept(
    generated: list[GeneratedCard], batch: list[Passage]
) -> tuple[list[Card], dict[str, int]]:
    """The cards that pass the grounding and format checks, and why the others were dropped."""
    dropped: dict[str, int] = {}
    cards: list[Card] = []

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for g in generated:
        sources: list[dict[str, Any]] = []
        for s in g.sources:
            if not 1 <= s.passage <= len(batch):
                continue
            passage = batch[s.passage - 1]
            quote = _normal(s.quote)
            if len(quote) < 8 or quote not in _normal(passage.content):
                continue
            if any(src["chunk_id"] == passage.chunk_id for src in sources):
                continue
            sources.append(
                {
                    "chunk_id": passage.chunk_id,
                    "quote": s.quote.strip(),
                    "heading_path": passage.heading_path,
                    "locations": passage.locations,
                }
            )
        if not sources:
            drop("unsupported")
            continue

        prompt, answer = g.prompt.strip(), g.answer.strip()
        choices: list[str] = []
        if not prompt or not answer:
            drop("empty")
            continue
        if g.kind == "cloze":
            spans = _CLOZE.findall(prompt)
            if len(spans) != 1 or not spans[0].strip():
                drop("cloze format")
                continue
            answer = spans[0].strip()
        if g.kind == "mcq":
            distractors = [d.strip() for d in g.distractors if d.strip()]
            options = [answer, *distractors]
            if len(distractors) != 3 or len({o.casefold() for o in options}) != 4:
                drop("mcq choices")
                continue
            # Shuffled the same way every time for the same question.
            random.Random(prompt).shuffle(options)
            choices = options

        cards.append(Card(g.kind, g.concept.strip(), prompt, answer, choices, sources))

    return cards, dropped


_STOPWORDS = frozenset(
    {
        *("a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it"),
        *("its", "of", "on", "or", "that", "the", "these", "this", "to", "what", "which", "with"),
    }
)
# Cards with the same answer whose questions share at least this much wording (the answer's
# own words aside) test the same fact. On generated chapters every same-answer pair was a
# repeat, overlapping 0.22 to 0.50; a different question with the same answer ("Which
# structure is cut in split-brain surgery?") shares next to nothing.
SAME_FACT_OVERLAP = 0.15


def _words(text: str) -> set[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    return {w for w in re.findall(r"[a-z0-9]+", text) if w not in _STOPWORDS}


def _same_fact(a: Card, b: Card) -> bool:
    if _normal(a.prompt) == _normal(b.prompt):
        return True
    if _normal(a.answer) != _normal(b.answer):
        return False
    answer = _words(a.answer)
    x, y = _words(a.prompt) - answer, _words(b.prompt) - answer
    return bool(x | y) and len(x & y) / len(x | y) >= SAME_FACT_OVERLAP


def distinct(cards: list[Card]) -> tuple[list[Card], int]:
    """A chapter's cards without repeats, keeping the first of each. Batches are written
    independently, so the same fact can come back from two of them."""
    kept: list[Card] = []
    for card in cards:
        if not any(_same_fact(card, k) for k in kept):
            kept.append(card)
    return kept, len(cards) - len(kept)

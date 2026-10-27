"""Answering a question from retrieved passages, with citations (decisions D2 and D27).

An answer is grounded when it cites the course material. When the material doesn't cover
the question, the model opens with a marker and answers from general knowledge; the marker
is removed and the answer is labeled as not from the student's course materials instead.
(Citations alone can't tell: an off-topic answer may still cite a passing mention.)
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from engram.chat.retrieve import Passage
from engram.llm import Provider, Usage
from engram.llm.base import Cite, Document, TextDelta, Turn

PROMPT_VERSION = "chat-v2"

MARKER = "[not in course materials]"

SYSTEM = f"""\
You help a student who is stuck on something in their course. The documents are passages \
from their own course materials (textbook, slides, notes), found by searching for their \
question.

Answer from the documents, citing them. Explain plainly, like a good tutor: a direct answer \
first, then just enough explanation to make it make sense. Use short paragraphs and usually \
under 150 words. Use the course's own terms. Write plain text: no Markdown, no bold, \
headings or bullet symbols. If steps help, number them, one per line.

If the documents don't answer the question, start your reply with exactly {MARKER} on its \
own line, then answer from general knowledge without citations. Don't cite a document for \
something it doesn't say or only mentions in passing.\
"""


@dataclass(frozen=True)
class Source:
    """A passage the answer cites, numbered in the order it is first cited."""

    number: int
    passage: Passage


@dataclass(frozen=True)
class Text:
    block: int
    text: str


@dataclass(frozen=True)
class Cited:
    """`block` of the answer is supported by `source`, which says `quote`."""

    block: int
    source: Source
    first: bool
    quote: str


@dataclass(frozen=True)
class Outside:
    """The answer isn't from the course materials. Comes before any of its text."""


Event = Text | Cited | Outside


def search_text(question: str, history: list[Turn]) -> str:
    """What to search for: a follow-up ("why?") needs the question before it."""
    earlier = [t.text for t in history if t.role == "user"][-1:]
    return " ".join([*earlier, question])


async def answer(
    provider: Provider,
    model: str,
    question: str,
    history: list[Turn],
    passages: list[Passage],
    usage: Usage,
) -> AsyncIterator[Event]:
    sources: dict[int, Source] = {}
    documents = [Document(p.title, p.text) for p in passages]
    stream = provider.cited(
        model, system=SYSTEM, documents=documents, history=history, question=question, usage=usage
    )
    # Events are held back until the opening text shows whether it's the marker.
    held: list[Event] = []
    opening = ""
    decided = False
    # After the marker, the blank lines that follow it are dropped too.
    trim = False
    async for event in stream:
        match event:
            case TextDelta(block, text):
                if decided:
                    if trim:
                        text = text.lstrip()
                        trim = not text
                    if text:
                        yield Text(block, text)
                    continue
                opening += text
                held.append(Text(block, text))
                start = opening.lstrip()
                if start.startswith(MARKER):
                    decided = True
                    yield Outside()
                    for e in held:
                        if isinstance(e, Cited):
                            yield e
                    if rest := start.removeprefix(MARKER).lstrip():
                        yield Text(block, rest)
                    else:
                        trim = True
                elif not MARKER.startswith(start):
                    decided = True
                    for e in held:
                        yield e
            case Cite(block, document, quote) if 0 <= document < len(passages):
                source = sources.get(document)
                first = source is None
                if source is None:
                    source = sources[document] = Source(len(sources) + 1, passages[document])
                cited = Cited(block, source, first, quote)
                if decided:
                    yield cited
                else:
                    held.append(cited)
    if not decided:
        for e in held:
            yield e

"""Review scheduling with FSRS, and the daily shape of a student's reviews.

FSRS decides when each card comes back. Around it, two rules keep reviews manageable:
new cards are introduced a few at a time each day, and a card in its first short steps
(minutes apart) can be shown a little early, so a session doesn't stall waiting for it.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import fsrs

# New cards a student starts per day. Each new card brings several reviews in its first
# weeks, so this bounds the daily load: 20 a day settles at roughly 15 minutes of review.
NEW_PER_DAY = 20
# Cards in their learning steps may be shown this early.
LEARN_AHEAD = timedelta(minutes=20)
# For "about N minutes": a typical review, answer and rating included.
SECONDS_PER_CARD = 20

State = Literal["learning", "review", "relearning"]

_scheduler = fsrs.Scheduler()
# Without fuzzing, so the "when you'll see it again" labels are stable.
_preview = fsrs.Scheduler(enable_fuzzing=False)


@dataclass(frozen=True)
class Progress:
    state: State
    step: int | None
    stability: float | None
    difficulty: float | None
    due: datetime
    last_review: datetime | None


def _card(progress: Progress | None, now: datetime) -> fsrs.Card:
    if progress is None:
        return fsrs.Card(due=now)
    return fsrs.Card(
        state=fsrs.State[progress.state.capitalize()],
        step=progress.step,
        stability=progress.stability,
        difficulty=progress.difficulty,
        due=progress.due,
        last_review=progress.last_review,
    )


def _progress(card: fsrs.Card) -> Progress:
    state: State = card.state.name.lower()  # type: ignore[assignment]
    return Progress(state, card.step, card.stability, card.difficulty, card.due, card.last_review)


def review(progress: Progress | None, rating: int, now: datetime) -> Progress:
    """The card's progress after a review rated 1 (forgot) to 4 (easy)."""
    card, _ = _scheduler.review_card(_card(progress, now), fsrs.Rating(rating), now)
    return _progress(card)


def preview(progress: Progress | None, now: datetime) -> dict[int, datetime]:
    """When the card would next be due for each rating, to label the rating buttons."""
    card = _card(progress, now)
    return {r.value: _preview.review_card(card, r, now)[0].due for r in fsrs.Rating}


def timezone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


@dataclass(frozen=True)
class Day:
    """The student's current day, as instants: reviews due today count as due now."""

    now: datetime
    start: datetime
    end: datetime

    @classmethod
    def of(cls, now: datetime, tz: ZoneInfo) -> "Day":
        local = now.astimezone(tz)
        start = datetime.combine(local.date(), time(), tz)
        return cls(now, start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC))

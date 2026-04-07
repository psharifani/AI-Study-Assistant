"""
SuperMemo-2 (SM-2) spaced repetition.

Quality q is 0–5 (0 = complete blackout, 5 = perfect response).
If q < 3 the card is treated as failed: repetitions reset, next review in 1 day.
If q >= 3 the interval follows the SM-2 schedule and ease factor is updated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class SM2State:
    ease_factor: float
    interval_days: float
    repetitions: int


def clamp_quality(q: int) -> int:
    return max(0, min(5, q))


def next_sm2_state(
    quality: int,
    ease_factor: float,
    interval_days: float,
    repetitions: int,
) -> SM2State:
    """Compute new SM-2 parameters after a review. Does not set wall-clock time."""
    q = clamp_quality(quality)
    ef = ease_factor if ease_factor >= 1.3 else 1.3

    if q < 3:
        return SM2State(ease_factor=ef, interval_days=1.0, repetitions=0)

    n = repetitions
    if n == 0:
        new_interval = 1.0
    elif n == 1:
        new_interval = 6.0
    else:
        new_interval = max(1.0, round(interval_days * ef))

    new_n = n + 1
    new_ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    if new_ef < 1.3:
        new_ef = 1.3

    return SM2State(ease_factor=new_ef, interval_days=float(new_interval), repetitions=new_n)


def apply_sm2_review(
    quality: int,
    ease_factor: float,
    interval_days: float,
    repetitions: int,
) -> tuple[SM2State, datetime]:
    """Returns new SM-2 state and when this card should be reviewed again (UTC)."""
    state = next_sm2_state(quality, ease_factor, interval_days, repetitions)
    next_at = datetime.now(timezone.utc) + timedelta(days=state.interval_days)
    return state, next_at

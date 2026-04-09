"""Unit tests for SM-2 helpers (isolated pure logic)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

from sm2 import (
    AGAIN_MINUTES,
    SM2State,
    apply_four_button_review,
    apply_sm2_review,
    clamp_quality,
    next_sm2_state,
)


class TestClampQualityLow(TestCase):
    def test_clamps_negative_to_zero(self) -> None:
        self.assertEqual(clamp_quality(-10), 0)


class TestClampQualityHigh(TestCase):
    def test_clamps_above_five_to_five(self) -> None:
        self.assertEqual(clamp_quality(99), 5)


class TestClampQualityMid(TestCase):
    def test_preserves_mid_range(self) -> None:
        self.assertEqual(clamp_quality(3), 3)


class TestNextSm2StateLapse(TestCase):
    def test_quality_below_three_resets_repetitions(self) -> None:
        s = next_sm2_state(2, 2.5, 10.0, 5)
        self.assertEqual(s.repetitions, 0)
        self.assertEqual(s.interval_days, 1.0)


class TestNextSm2StateFirstSuccess(TestCase):
    def test_first_success_interval_one_day(self) -> None:
        s = next_sm2_state(4, 2.5, 1.0, 0)
        self.assertEqual(s.repetitions, 1)
        self.assertEqual(s.interval_days, 1.0)


class TestNextSm2StateSecondSuccess(TestCase):
    def test_second_review_interval_six_days(self) -> None:
        s = next_sm2_state(4, 2.5, 1.0, 1)
        self.assertEqual(s.repetitions, 2)
        self.assertEqual(s.interval_days, 6.0)


class TestApplySm2ReviewReturnsUtc(TestCase):
    def test_advances_next_review_by_interval(self) -> None:
        fixed = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
        with patch("sm2.datetime") as m_dt:
            m_dt.now.return_value = fixed
            m_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            m_dt.timedelta = timedelta
            m_dt.timezone = timezone
            state, nxt = apply_sm2_review(4, 2.5, 1.0, 1)
        self.assertEqual(nxt, fixed + timedelta(days=state.interval_days))


class TestApplyFourButtonAgain(TestCase):
    def test_again_uses_ten_minutes_and_lowers_ease(self) -> None:
        fixed = datetime(2030, 6, 15, 9, 0, tzinfo=timezone.utc)
        with patch("sm2.datetime") as m_dt:
            m_dt.now.return_value = fixed
            m_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            m_dt.timedelta = timedelta
            m_dt.timezone = timezone
            state, nxt = apply_four_button_review("again", 2.5, 3.0, 2)
        self.assertEqual(nxt, fixed + timedelta(minutes=AGAIN_MINUTES))
        self.assertEqual(state.repetitions, 0)
        self.assertLess(state.ease_factor, 2.5)


class TestApplyFourButtonGood(TestCase):
    def test_good_maps_to_quality_four(self) -> None:
        fixed = datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc)
        with patch("sm2.datetime") as m_dt:
            m_dt.now.return_value = fixed
            m_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            m_dt.timedelta = timedelta
            m_dt.timezone = timezone
            state, _ = apply_four_button_review("good", 2.5, 1.0, 0)
        self.assertEqual(state.repetitions, 1)


class TestApplyFourButtonUnknownRating(TestCase):
    def test_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            apply_four_button_review("invalid", 2.5, 1.0, 0)


class TestSM2StateDataclass(TestCase):
    def test_is_frozen(self) -> None:
        s = SM2State(2.5, 3.0, 1)
        with self.assertRaises(Exception):
            s.ease_factor = 3.0  # type: ignore[misc]

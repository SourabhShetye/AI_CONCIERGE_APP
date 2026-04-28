"""
Tests for booking_service.py
Run with: python -m pytest tests/ -v --tb=short
"""
import os
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "placeholder_key")
os.environ.setdefault("GROQ_API_KEY", "placeholder_key")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_testing_only")
os.environ.setdefault("DEFAULT_RESTAURANT_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.booking_service import (
    validate_booking_time,
    check_duplicate_booking,
    can_cancel_booking,
    check_capacity,
)

DUBAI_TZ = ZoneInfo("Asia/Dubai")


def now_dubai():
    return datetime.now(DUBAI_TZ)


# ─── validate_booking_time ─────────────────────────────────────────────────────

class TestValidateBookingTime:

    def test_past_booking_rejected(self):
        past = now_dubai() - timedelta(hours=1)
        ok, err = validate_booking_time(past)
        assert not ok
        assert err != ""

    def test_too_soon_rejected(self):
        too_soon = now_dubai() + timedelta(minutes=30)
        ok, err = validate_booking_time(too_soon)
        assert not ok
        assert err != ""

    def test_valid_2_hours_30_min_ahead_accepted(self):
        valid = now_dubai() + timedelta(hours=2, minutes=30)
        ok, err = validate_booking_time(valid)
        assert ok
        assert err == ""

    def test_valid_3_days_ahead_accepted(self):
        valid = now_dubai() + timedelta(days=3)
        ok, _ = validate_booking_time(valid)
        assert ok

    def test_exactly_2_hours_minus_1_second_rejected(self):
        edge = now_dubai() + timedelta(hours=2, seconds=-1)
        ok, _ = validate_booking_time(edge)
        assert not ok

    def test_beyond_3_months_rejected(self):
        too_far = now_dubai() + timedelta(days=92)
        ok, err = validate_booking_time(too_far)
        assert not ok
        assert err != ""

    def test_3_months_minus_1_day_accepted(self):
        within = now_dubai() + timedelta(days=89)
        within = within.replace(hour=12, minute=0, second=0, microsecond=0)
        ok, _ = validate_booking_time(within)
        assert ok


# ─── check_duplicate_booking ──────────────────────────────────────────────────

class TestCheckDuplicateBooking:

    def _make_booking(self, user_id, hours_from_now, status="confirmed"):
        dt = now_dubai() + timedelta(hours=hours_from_now)
        return {
            "user_id": user_id,
            "booking_time": dt.isoformat(),
            "status": status,
        }

    def test_booking_within_2_hours_blocked(self):
        bookings = [self._make_booking("user1", 5)]
        target = now_dubai() + timedelta(hours=5, minutes=30)
        assert check_duplicate_booking(bookings, "user1", target) is True

    def test_booking_exactly_2_hours_apart_blocked(self):
        bookings = [self._make_booking("user1", 5)]
        target = now_dubai() + timedelta(hours=5) + timedelta(hours=1, minutes=59)
        assert check_duplicate_booking(bookings, "user1", target) is True

    def test_booking_over_2_hours_apart_allowed(self):
        bookings = [self._make_booking("user1", 5)]
        target = now_dubai() + timedelta(hours=8)
        assert check_duplicate_booking(bookings, "user1", target) is False

    def test_cancelled_booking_does_not_block(self):
        bookings = [self._make_booking("user1", 5, status="cancelled")]
        target = now_dubai() + timedelta(hours=5, minutes=30)
        assert check_duplicate_booking(bookings, "user1", target) is False

    def test_different_user_does_not_block(self):
        bookings = [self._make_booking("user2", 5)]
        target = now_dubai() + timedelta(hours=5)
        assert check_duplicate_booking(bookings, "user1", target) is False

    def test_empty_bookings_never_blocked(self):
        assert check_duplicate_booking([], "user1", now_dubai() + timedelta(hours=3)) is False

    def test_multiple_bookings_only_checks_own_user(self):
        bookings = [
            self._make_booking("user2", 5),
            self._make_booking("user3", 5),
        ]
        target = now_dubai() + timedelta(hours=5)
        assert check_duplicate_booking(bookings, "user1", target) is False


# ─── can_cancel_booking ───────────────────────────────────────────────────────

class TestCanCancelBooking:

    def test_cancellation_well_in_advance_allowed(self):
        future = now_dubai() + timedelta(hours=6)
        ok, _ = can_cancel_booking(future)
        assert ok

    def test_cancellation_1_day_ahead_allowed(self):
        future = now_dubai() + timedelta(days=1)
        ok, _ = can_cancel_booking(future)
        assert ok

    def test_cancellation_2_hours_ahead_blocked(self):
        soon = now_dubai() + timedelta(hours=2)
        ok, err = can_cancel_booking(soon)
        assert not ok
        assert err != ""

    def test_cancellation_past_booking_blocked(self):
        past = now_dubai() - timedelta(hours=1)
        ok, err = can_cancel_booking(past)
        assert not ok


# ─── check_capacity ───────────────────────────────────────────────────────────

class TestCheckCapacity:

    def _make_booking(self, hours_from_now, party_size, status="confirmed"):
        dt = now_dubai() + timedelta(hours=hours_from_now)
        return {
            "booking_time": dt.isoformat(),
            "party_size": party_size,
            "status": status,
        }

    def test_empty_restaurant_accepts_any_booking(self):
        ok, _ = check_capacity([], now_dubai() + timedelta(hours=3), 4, 10, 10)
        assert ok

    def test_party_exceeding_max_size_rejected(self):
        ok, err = check_capacity([], now_dubai() + timedelta(hours=3), 15, 10, 10)
        assert not ok
        assert err != ""

    def test_full_restaurant_rejects_new_booking(self):
        bookings = [self._make_booking(3, 2) for _ in range(10)]
        ok, err = check_capacity(
            bookings,
            now_dubai() + timedelta(hours=3),
            2,
            total_tables=10,
            max_party_size=10,
        )
        assert not ok

    def test_cancelled_bookings_do_not_count_towards_capacity(self):
        bookings = [self._make_booking(3, 2, status="cancelled") for _ in range(10)]
        ok, _ = check_capacity(
            bookings,
            now_dubai() + timedelta(hours=3),
            2,
            total_tables=10,
            max_party_size=10,
        )
        assert ok

    def test_bookings_at_different_time_do_not_conflict(self):
        bookings = [self._make_booking(3, 2) for _ in range(10)]
        ok, _ = check_capacity(
            bookings,
            now_dubai() + timedelta(hours=8),
            2,
            total_tables=10,
            max_party_size=10,
        )
        assert ok

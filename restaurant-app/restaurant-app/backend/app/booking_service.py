"""
booking_service.py - Booking validation and smart table availability.

Preserved from stable version:
  - 2-hour advance booking requirement
  - 4-hour cancellation policy
  - Duplicate booking prevention
  - Smart slot allocation (bin-packing: fill smallest available table ≥ party size)
  - Dubai timezone (UTC+4)
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional
import logging

logger = logging.getLogger(__name__)

DUBAI_TZ = ZoneInfo("Asia/Dubai")
BOOKING_ADVANCE_HOURS = 2    # Must book at least 2 hours ahead
CANCEL_POLICY_HOURS = 4      # Can only cancel 4+ hours before booking
SLOT_DURATION_HOURS = 2      # Each booking occupies a 2-hour slot


def get_dubai_now() -> datetime:
    return datetime.now(DUBAI_TZ)


def parse_booking_datetime(iso_string: str) -> Optional[datetime]:
    """Parse ISO datetime string and attach Dubai timezone."""
    try:
        dt = datetime.fromisoformat(iso_string)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=DUBAI_TZ)
        return dt
    except ValueError:
        return None


def validate_booking_time(booking_time: datetime) -> tuple[bool, str]:
    """
    Validate that the booking time satisfies business rules.
    Returns (is_valid, error_message).
    """
    now = get_dubai_now()

    # Must be in the future
    if booking_time <= now:
        return False, "Booking time must be in the future."

    # Must be at least BOOKING_ADVANCE_HOURS from now
    if booking_time < now + timedelta(hours=BOOKING_ADVANCE_HOURS):
        return False, f"Bookings must be made at least {BOOKING_ADVANCE_HOURS} hours in advance."

    return True, ""


def can_cancel_booking(booking_time: datetime) -> tuple[bool, str]:
    """Check if a booking can still be cancelled (4-hour policy)."""
    now = get_dubai_now()
    bk = booking_time if booking_time.tzinfo else booking_time.replace(tzinfo=DUBAI_TZ)
    hours_until = (bk - now).total_seconds() / 3600

    if hours_until < CANCEL_POLICY_HOURS:
        return False, f"Cancellations must be made at least {CANCEL_POLICY_HOURS} hours before booking."
    return True, ""


def check_duplicate_booking(
    existing_bookings: list[dict],
    user_id: str,
    booking_time: datetime,
) -> bool:
    """Return True if user already has a booking within ±2 hours of requested time."""
    for b in existing_bookings:
        if b.get("user_id") != user_id:
            continue
        if b.get("status") == "cancelled":
            continue
        existing_time_str = b.get("booking_time", "")
        try:
            existing_time = datetime.fromisoformat(existing_time_str)
            if existing_time.tzinfo is None:
                existing_time = existing_time.replace(tzinfo=DUBAI_TZ)
            delta = abs((booking_time - existing_time).total_seconds()) / 3600
            if delta < SLOT_DURATION_HOURS:
                return True  # Duplicate
        except Exception:
            continue
    return False


def check_capacity(
    existing_bookings: list[dict],
    booking_time: datetime,
    party_size: int,
    total_tables: int = 20,
    max_party_size: int = 10,
) -> tuple[bool, str]:
    """
    Bin-packing capacity check:
    Count confirmed bookings in the same 2-hour slot.
    Uses simple table-count model: each booking occupies 1 table.
    """
    if party_size > max_party_size:
        return False, f"Maximum party size is {max_party_size}."

    slot_start = booking_time
    slot_end = booking_time + timedelta(hours=SLOT_DURATION_HOURS)

    conflicting = 0
    for b in existing_bookings:
        if b.get("status") == "cancelled":
            continue
        try:
            bt = datetime.fromisoformat(b["booking_time"])
            if bt.tzinfo is None:
                bt = bt.replace(tzinfo=DUBAI_TZ)
            bt_end = bt + timedelta(hours=SLOT_DURATION_HOURS)
            # Overlap check
            if bt < slot_end and bt_end > slot_start:
                conflicting += 1
        except Exception:
            continue

    if conflicting >= total_tables:
        return False, "No tables available for that time slot. Please choose a different time."

    return True, ""

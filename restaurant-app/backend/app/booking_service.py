"""
booking_service.py - Booking validation and smart table availability.

Feature 3 update: Smart table allocation using bin-packing.
- Finds the smallest table that fits the party (no splitting across tables)
- Returns available slots if requested time is full
- Returns the assigned table_id and table_number
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional
import logging

logger = logging.getLogger(__name__)

DUBAI_TZ = ZoneInfo("Asia/Dubai")
BOOKING_ADVANCE_HOURS = 2
CANCEL_POLICY_HOURS = 4
SLOT_DURATION_HOURS = 2


def get_dubai_now() -> datetime:
    return datetime.now(DUBAI_TZ)


def parse_booking_datetime(iso_string: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(iso_string)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=DUBAI_TZ)
        return dt
    except ValueError:
        return None


def validate_booking_time(booking_time: datetime) -> tuple[bool, str]:
    now = get_dubai_now()
    if booking_time <= now:
        return False, "Booking time must be in the future."
    if booking_time < now + timedelta(hours=BOOKING_ADVANCE_HOURS):
        earliest = now + timedelta(hours=BOOKING_ADVANCE_HOURS)
        return False, (
            f"Bookings must be made at least {BOOKING_ADVANCE_HOURS} hours in advance. "
            f"The earliest available slot is {earliest.strftime('%d %B at %I:%M %p')}."
        )

    # Must not be more than 3 months in advance
    three_months_ahead = now + timedelta(days=90)
    # Use end of that day as the cutoff so the boundary date itself is bookable
    three_months_end = three_months_ahead.replace(hour=23, minute=59, second=59)
    if booking_time > three_months_end:
        return False, (
            f"Bookings can only be made up to 3 months in advance. "
            f"The latest available date is {three_months_ahead.strftime('%d %B %Y')}."
        )

    return True, ""


def can_cancel_booking(booking_time: datetime) -> tuple[bool, str]:
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
    """
    Return True only if user has an ACTIVE (non-cancelled, non-completed)
    booking within ±2 hours of the requested time.
    """
    for b in existing_bookings:
        if b.get("user_id") != user_id:
            continue
        # Only block on active bookings
        if b.get("status") in ("cancelled", "completed"):
            continue
        existing_time_str = b.get("booking_time", "")
        try:
            existing_time = datetime.fromisoformat(existing_time_str)
            if existing_time.tzinfo is None:
                existing_time = existing_time.replace(tzinfo=DUBAI_TZ)
            delta = abs((booking_time - existing_time).total_seconds()) / 3600
            if delta < SLOT_DURATION_HOURS:
                return True
        except Exception:
            continue
    return False

# ─── NEW: Smart table allocation ──────────────────────────────────────────────

def get_tables_booked_in_slot(
    existing_bookings: list[dict],
    booking_time: datetime,
) -> set[str]:
    """
    Returns set of table_ids already booked in the 2-hour slot
    containing booking_time.
    """
    slot_start = booking_time
    slot_end = booking_time + timedelta(hours=SLOT_DURATION_HOURS)
    booked_table_ids = set()

    for b in existing_bookings:
        if b.get("status") == "cancelled":
            continue
        # Only consider bookings with an assigned table
        table_id = b.get("assigned_table_id")
        if not table_id:
            continue
        try:
            bt = datetime.fromisoformat(b["booking_time"])
            if bt.tzinfo is None:
                bt = bt.replace(tzinfo=DUBAI_TZ)
            bt_end = bt + timedelta(hours=SLOT_DURATION_HOURS)
            if bt < slot_end and bt_end > slot_start:
                booked_table_ids.add(table_id)
        except Exception:
            continue

    return booked_table_ids


def find_best_table(
    tables: list[dict],
    party_size: int,
    booked_table_ids: set[str],
) -> Optional[dict]:
    """
    Bin-packing: find the smallest available table that fits the party.

    Rules:
    - Table capacity must be >= party_size
    - Table must not be booked in this slot
    - Table must be active
    - Among valid tables, pick the one with lowest capacity (closest fit)
    - Never split a party across multiple tables

    Returns the table dict or None if no suitable table available.
    """
    available = [
        t for t in tables
        if t.get("is_active", True)
        and t["id"] not in booked_table_ids
        and int(t["capacity"]) >= party_size
    ]

    if not available:
        return None

    # Sort by capacity ascending — pick the closest fit (bin-packing)
    available.sort(key=lambda t: int(t["capacity"]))
    return available[0]


def get_available_slots(
    tables: list[dict],
    existing_bookings: list[dict],
    party_size: int,
    date: datetime,
    opening_hour: int = 12,
    closing_hour: int = 23,
) -> list[str]:
    """
    Return list of available time slots on a given date for the party size.
    Checks every hour from opening to closing - SLOT_DURATION_HOURS.
    """
    available_slots = []

    for hour in range(opening_hour, closing_hour - SLOT_DURATION_HOURS + 1):
        slot_time = date.replace(hour=hour, minute=0, second=0, microsecond=0)
        if slot_time.tzinfo is None:
            slot_time = slot_time.replace(tzinfo=DUBAI_TZ)

        # Skip past times
        if slot_time <= get_dubai_now() + timedelta(hours=BOOKING_ADVANCE_HOURS):
            continue

        booked_ids = get_tables_booked_in_slot(existing_bookings, slot_time)
        table = find_best_table(tables, party_size, booked_ids)
        if table:
            available_slots.append(slot_time.strftime("%I:%M %p"))

    return available_slots


def check_capacity(
    existing_bookings: list[dict],
    booking_time: datetime,
    party_size: int,
    total_tables: int = 20,
    max_party_size: int = 10,
) -> tuple[bool, str]:
    """
    Legacy capacity check — used when no tables_inventory is configured.
    Falls back to simple table count model.
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
            if bt < slot_end and bt_end > slot_start:
                conflicting += 1
        except Exception:
            continue

    if conflicting >= total_tables:
        return False, "No tables available for that time slot. Please choose a different time."

    return True, ""

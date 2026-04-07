"""
crm.py - CRM logic: tag computation, visit tracking, milestone rewards.

Tags:
  - Frequent Diner  → visit_count >= 5
  - Big Spender     → total_spend >= 500
  - VIP             → both of the above
  - Churn Risk      → last_visit > 30 days ago

Called when a table is closed (payment processed).
"""

from datetime import datetime, timezone
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def compute_tags(visit_count: int, total_spend: float, last_visit) -> list[str]:
    tags = []
    is_frequent = visit_count >= 5
    is_big_spender = total_spend >= 500

    if is_frequent and is_big_spender:
        tags.append("VIP")
    else:
        if is_frequent:
            tags.append("Frequent Diner")
        if is_big_spender:
            tags.append("Big Spender")

    if last_visit:
        try:
            # Handle both string and datetime objects coming from Supabase
            if isinstance(last_visit, str):
                from datetime import datetime
                # Remove trailing Z and parse
                last_visit = last_visit.replace("Z", "+00:00")
                last = datetime.fromisoformat(last_visit)
            else:
                last = last_visit

            now = datetime.now(timezone.utc)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            days_since = (now - last).days
            if days_since > 30:
                tags.append("Churn Risk")
        except Exception:
            pass  # If date parsing fails, just skip the Churn Risk tag

    return tags


def get_milestone_message(visit_count: int) -> Optional[str]:
    """Return a personalised milestone message on special visit numbers."""
    milestones = {
        5:  "🎉 This is your 5th visit! You're now a Frequent Diner!",
        10: "🌟 10 visits! You're a VIP member now!",
        20: "🏆 20 visits! You're legendary!",
        50: "👑 50 visits! Welcome back, legend!",
    }
    return milestones.get(visit_count)


def build_welcome_message(name: str, visit_count: int, tags: list) -> str:
    if visit_count == 0:
        return f"Welcome, {name}! Great to have you here 🍽️"
    milestone = get_milestone_message(visit_count)
    if milestone:
        return f"Welcome back, {name}! {milestone}"
    tag_str = f" ({', '.join(tags)})" if tags else ""
    return f"Welcome back, {name}!{tag_str} 🍽️"
    # Removed: "This is your visit #N" — unnecessary and confusing

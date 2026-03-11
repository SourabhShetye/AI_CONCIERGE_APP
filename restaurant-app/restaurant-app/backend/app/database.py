"""
database.py - Supabase client singleton
All DB access goes through the `db` object exposed here.
"""

from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_db() -> Client:
    """Return the Supabase client, creating it on first call."""
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


# Convenience alias used throughout the app
db: Client = None  # type: ignore


def init_db():
    """Call once at startup to initialise the client."""
    global db
    db = get_db()

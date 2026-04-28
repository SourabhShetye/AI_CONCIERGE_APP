"""
Tests for auth.py
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
import hashlib
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)


# ─── Password hashing ─────────────────────────────────────────────────────────

class TestPasswordHashing:

    def test_correct_pin_verifies(self):
        hashed = hash_password("1234")
        assert verify_password("1234", hashed)

    def test_wrong_pin_fails(self):
        hashed = hash_password("1234")
        assert not verify_password("5678", hashed)

    def test_hash_is_not_plaintext(self):
        hashed = hash_password("1234")
        assert hashed != "1234"

    def test_bcrypt_uses_random_salt_so_two_hashes_differ(self):
        h1 = hash_password("1234")
        h2 = hash_password("1234")
        assert h1 != h2

    def test_empty_pin_still_hashes(self):
        hashed = hash_password("")
        assert isinstance(hashed, str)
        assert len(hashed) > 10

    def test_special_characters_in_pin_work(self):
        hashed = hash_password("!@#$")
        assert verify_password("!@#$", hashed)
        assert not verify_password("1234", hashed)


# ─── JWT create and decode ────────────────────────────────────────────────────

class TestJWTTokens:

    def _make_token(self, overrides=None):
        payload = {
            "user_id": "user-abc-123",
            "role": "customer",
            "restaurant_id": "rest-xyz-456",
            "name": "Test User",
        }
        if overrides:
            payload.update(overrides)
        return create_access_token(payload)

    def test_create_and_decode_round_trip(self):
        token = self._make_token()
        payload = decode_token(token)
        assert payload["user_id"] == "user-abc-123"
        assert payload["role"] == "customer"
        assert payload["restaurant_id"] == "rest-xyz-456"

    def test_name_preserved_in_token(self):
        token = self._make_token()
        payload = decode_token(token)
        assert payload["name"] == "Test User"

    def test_staff_role_preserved(self):
        token = self._make_token({"role": "admin"})
        payload = decode_token(token)
        assert payload["role"] == "admin"

    def test_tampered_signature_raises(self):
        token = self._make_token()
        # Corrupt the last 5 chars of the signature
        bad = token[:-5] + "XXXXX"
        with pytest.raises(Exception):
            decode_token(bad)

    def test_completely_invalid_string_raises(self):
        with pytest.raises(Exception):
            decode_token("not.a.jwt")

    def test_empty_string_raises(self):
        with pytest.raises(Exception):
            decode_token("")

    def test_different_payloads_produce_different_tokens(self):
        t1 = self._make_token({"user_id": "user-1"})
        t2 = self._make_token({"user_id": "user-2"})
        assert t1 != t2

    def test_token_contains_exp_claim(self):
        token = self._make_token()
        payload = decode_token(token)
        assert "exp" in payload


# ─── Refresh token hash helper ────────────────────────────────────────────────
# Tests _hash_refresh_token only if it is exported from auth.py.
# If the function is private/not exported, this block is skipped gracefully.

try:
    from app.auth import _hash_refresh_token
    _HASH_AVAILABLE = True
except ImportError:
    _HASH_AVAILABLE = False


@pytest.mark.skipif(not _HASH_AVAILABLE, reason="_hash_refresh_token not exported from auth.py")
class TestRefreshTokenHash:

    def test_output_is_64_char_hex(self):
        result = _hash_refresh_token("some_token")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_matches_sha256(self):
        raw = "my_refresh_token_value"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert _hash_refresh_token(raw) == expected

    def test_different_inputs_produce_different_hashes(self):
        assert _hash_refresh_token("token_a") != _hash_refresh_token("token_b")

    def test_same_input_always_same_output(self):
        raw = "stable_token"
        assert _hash_refresh_token(raw) == _hash_refresh_token(raw)

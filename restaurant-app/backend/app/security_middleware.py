"""
security_middleware.py — New file: backend/app/security_middleware.py

Create this file. It centralises all security middleware, rate limiting,
injection detection, and audit logging. Import it in main.py.
"""

import re
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SECURITY HEADERS MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════════

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to every response.
    Add to main.py: app.add_middleware(SecurityHeadersMiddleware)
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent browsers caching sensitive API responses
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        # HSTS — force HTTPS for 1 year
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Block clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Control referrer info
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Limit browser features — only allow microphone for voice input
        response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"

        return response


# ═══════════════════════════════════════════════════════════════════════════════
# 2. IN-MEMORY RATE LIMITER
# (Works on single Render instance — upgrade to Redis for multi-worker)
# ═══════════════════════════════════════════════════════════════════════════════

class InMemoryRateLimiter:
    """
    Simple sliding-window rate limiter keyed by IP + endpoint.
    For production multi-worker: replace with Redis-backed slowapi.
    """

    def __init__(self):
        self._windows: dict = defaultdict(list)

    def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=window_seconds)

        # Clean expired entries
        self._windows[key] = [t for t in self._windows[key] if t > cutoff]

        if len(self._windows[key]) >= limit:
            return False

        self._windows[key].append(now)
        return True

    def check(
        self,
        request: Request,
        limit: int,
        window_seconds: int,
        scope: str = "",
    ):
        """Raise 429 if rate limit exceeded."""
        ip = request.client.host if request.client else "unknown"
        key = f"{ip}:{scope or request.url.path}"

        if not self.is_allowed(key, limit, window_seconds):
            logger.warning(
                f"RATE_LIMIT_EXCEEDED: ip={ip} endpoint={request.url.path}"
            )
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait before trying again.",
                headers={"Retry-After": str(window_seconds)},
            )


# Single global instance
rate_limiter = InMemoryRateLimiter()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PROMPT INJECTION & JAILBREAK DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

INJECTION_PATTERNS = [
    # Classic instruction override
    r"ignore\s+(all\s+)?(previous|prior|above|prior)\s+instructions",
    r"disregard\s+(your\s+)?(system\s+)?prompt",
    r"forget\s+(everything|all|your\s+instructions)",
    r"override\s*(mode|instructions|system|prompt)",
    # Role takeover
    r"you\s+are\s+now\s+(a|an)\s+\w",
    r"act\s+as\s+(if\s+you\s+are\s+)?(a|an)\s+\w",
    r"new\s+role\s*:",
    r"pretend\s+(you\s+are|to\s+be)\s+",
    # DAN / jailbreak patterns
    r"\bdan\b.{0,20}(mode|now|enabled|activated)",
    r"do\s+anything\s+now",
    r"developer\s+mode",
    r"jailbreak",
    r"no\s+restrictions",
    r"unrestricted\s+(mode|access|ai)",
    # System prompt extraction
    r"(repeat|show|display|reveal|print|output)\s+.{0,30}(system\s+prompt|instructions)",
    r"what\s+(are\s+your|were\s+your)\s+(instructions|prompt|rules)",
    r"(beginning|start)\s+of\s+(your\s+)?(conversation|context|prompt)",
    # Llama/instruction tokens
    r"<\s*system\s*>",
    r"<\s*/\s*system\s*>",
    r"\[INST\]",
    r"\[\/INST\]",
    r"<<SYS>>",
    # Data exfiltration probes
    r"(list|show|give\s+me)\s+all\s+(customer|user|allerg)",
    r"(what\s+data|what\s+information)\s+(do\s+you\s+have|is\s+stored)",
    # Research/educational bypass attempts
    r"for\s+(educational|research|academic|university|testing)\s+purposes",
    r"(hypothetically|theoretically)\s+(speaking\s*)?,?\s+(if\s+you\s+had\s+no|imagine)",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in INJECTION_PATTERNS]


def sanitise_user_input(text: str, context: str = "user_message") -> str:
    """
    Sanitise text before injection into LLM prompt.
    - Strips Unicode control characters
    - Detects injection/jailbreak patterns
    - Enforces maximum length
    Raises HTTPException(400) if injection detected.
    Returns sanitised text if clean.
    """
    if not text:
        return text

    # Strip null bytes and control characters (keep newlines and tabs)
    text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]", "", text)

    # Enforce maximum length — prevents context stuffing
    if len(text) > 2000:
        logger.warning(f"SECURITY: Input truncated context={context} length={len(text)}")
        text = text[:2000]

    # Check injection patterns
    for pattern in COMPILED_PATTERNS:
        if pattern.search(text):
            logger.warning(
                f"SECURITY_EVENT: Injection pattern detected. "
                f"context={context} pattern={pattern.pattern[:50]} "
                f"input_preview={text[:100]!r}"
            )
            # Do NOT reveal why the message was rejected
            raise HTTPException(
                status_code=400,
                detail="Your message could not be processed. "
                       "Please describe your order or question differently.",
            )

    return text


def sanitise_admin_context(text: str) -> str:
    """
    Stricter sanitisation for restaurant admin ai_context field.
    Admins get slightly more trust but injection is still blocked.
    """
    if not text:
        return text

    text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]", "", text)

    # Hard length cap for context injection
    if len(text) > 1000:
        text = text[:1000]
        logger.warning("SECURITY: Admin ai_context truncated to 1000 chars")

    # Check all patterns — admins still cannot inject
    for pattern in COMPILED_PATTERNS:
        if pattern.search(text):
            logger.warning(
                f"SECURITY_EVENT: Admin context injection attempt. "
                f"pattern={pattern.pattern[:50]}"
            )
            raise HTTPException(
                status_code=400,
                detail="AI context contains prohibited content. "
                       "Use plain text describing your restaurant's specials and policies.",
            )

    return text


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SECURITY EVENT TRACKER (escalating attack detection)
# ═══════════════════════════════════════════════════════════════════════════════

class SecurityEventTracker:
    """
    Tracks security events per user. Triggers session suspension
    after repeated violations within a time window.
    """

    def __init__(self):
        self._events: dict = defaultdict(list)

    def record(self, user_id: str, event_type: str, ip: str = ""):
        self._events[user_id].append({
            "type": event_type,
            "timestamp": datetime.utcnow(),
            "ip": ip,
        })

    def violation_count(self, user_id: str, window_minutes: int = 10) -> int:
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        recent = [e for e in self._events[user_id] if e["timestamp"] > cutoff]
        return len(recent)

    def should_suspend(self, user_id: str) -> bool:
        """Suspend after 3 security events in 10 minutes."""
        return self.violation_count(user_id) >= 3


security_tracker = SecurityEventTracker()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. AUDIT LOGGER
# ═══════════════════════════════════════════════════════════════════════════════

async def audit_log(
    db,
    actor_id: str,
    actor_role: str,
    action: str,
    resource_type: str,
    resource_id: str,
    restaurant_id: str,
    ip_address: str,
    outcome: str,              # "success" | "failure" | "blocked"
    details: Optional[dict] = None,
):
    """
    Write an immutable audit record.
    Call this for: login/logout, table close, CRM access, PII access,
    account deletion, failed auth, security events.
    """
    try:
        db.table("audit_log").insert({
            "timestamp": datetime.utcnow().isoformat(),
            "actor_id": actor_id,
            "actor_role": actor_role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "restaurant_id": restaurant_id,
            "ip_address": ip_address,
            "outcome": outcome,
            "details": json.dumps(details or {}),
        }).execute()
    except Exception as e:
        # Audit failure is critical — log but never raise (don't block the request)
        logger.critical(
            f"AUDIT_LOG_FAILURE action={action} actor={actor_id} error={e}"
        )

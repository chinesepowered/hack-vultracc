"""Passwords (scrypt), signed session tokens, approval signatures, rate limits."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque

from .config import settings

SESSION_COOKIE = "tieout_session"
SESSION_TTL_S = 12 * 3600


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, dk_b64 = stored.split("$")
        salt, dk = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
    except ValueError:
        return False
    got = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=len(dk))
    return hmac.compare_digest(got, dk)


def _sign(data: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(settings.session_secret.encode(), data, hashlib.sha256).digest()).decode().rstrip("=")


def make_session(user_id: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"uid": user_id, "exp": int(time.time()) + SESSION_TTL_S}).encode()).decode().rstrip("=")
    return body + "." + _sign(body.encode())


def read_session(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(body.encode())):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except Exception:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data.get("uid")


def sign_approval(payload: dict) -> str:
    """HMAC-SHA256 over the canonical approval record (run, decision, reviewer, output hashes, time)."""
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(settings.session_secret.encode(), canon, hashlib.sha256).hexdigest()


class RateLimiter:
    """Sliding window limiter, in memory (single API process)."""

    def __init__(self) -> None:
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        now = time.time()
        q = self.hits[key]
        while q and q[0] < now - window_s:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


limiter = RateLimiter()

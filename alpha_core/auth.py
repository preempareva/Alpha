"""Shared signed-cookie session primitives; application code resolves users server-side."""

from __future__ import annotations

import hmac
import secrets
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


class InvalidSession(ValueError):
    """A signed cookie is missing a valid subject or has expired."""


class InvalidCsrfToken(ValueError):
    """A session-bound CSRF token is invalid, expired, or belongs to another user."""


class SignedSessionCodec:
    def __init__(self, secret: str, *, salt: str, max_age_seconds: int) -> None:
        if not secret:
            raise ValueError("session signing secret is required")
        if not salt or max_age_seconds < 1:
            raise ValueError("session salt and positive max age are required")
        self._serializer = URLSafeTimedSerializer(secret, salt=salt)
        self._csrf_serializer = URLSafeTimedSerializer(secret, salt=f"{salt}:csrf-v1")
        self.max_age_seconds = max_age_seconds

    def issue(self, subject: str) -> str:
        if not subject or len(subject) > 200:
            raise ValueError("session subject is invalid")
        return self._serializer.dumps({"sub": subject})

    def read_subject(self, token: str) -> str:
        try:
            claims: Any = self._serializer.loads(token, max_age=self.max_age_seconds)
        except (BadSignature, SignatureExpired) as exc:
            raise InvalidSession("signed session is invalid or expired") from exc
        if not isinstance(claims, dict) or not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise InvalidSession("signed session has no valid subject")
        return claims["sub"]

    def issue_csrf(self, subject: str) -> str:
        if not subject or len(subject) > 200:
            raise ValueError("CSRF subject is invalid")
        return self._csrf_serializer.dumps({"sub": subject, "purpose": "csrf", "nonce": secrets.token_urlsafe(24)})

    def verify_csrf(self, token: str, subject: str) -> None:
        try:
            claims: Any = self._csrf_serializer.loads(token, max_age=self.max_age_seconds)
        except (BadSignature, SignatureExpired) as exc:
            raise InvalidCsrfToken("CSRF token is invalid or expired") from exc
        if (not isinstance(claims, dict) or claims.get("purpose") != "csrf"
                or not isinstance(claims.get("sub"), str)
                or not hmac.compare_digest(claims["sub"], subject)
                or not isinstance(claims.get("nonce"), str)):
            raise InvalidCsrfToken("CSRF token does not match the authenticated user")

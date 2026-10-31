"""Shared signed-cookie session primitives; application code resolves users server-side."""

from __future__ import annotations

from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


class InvalidSession(ValueError):
    """A signed cookie is missing a valid subject or has expired."""


class SignedSessionCodec:
    def __init__(self, secret: str, *, salt: str, max_age_seconds: int) -> None:
        if not secret:
            raise ValueError("session signing secret is required")
        if not salt or max_age_seconds < 1:
            raise ValueError("session salt and positive max age are required")
        self._serializer = URLSafeTimedSerializer(secret, salt=salt)
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

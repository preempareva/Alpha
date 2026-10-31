from __future__ import annotations

import pytest
from itsdangerous import URLSafeTimedSerializer

from alpha_core.auth import InvalidCsrfToken, InvalidSession, SignedSessionCodec


def test_shared_codec_reads_existing_knowledge_session_cookie_shape():
    secret = "test-only-knowledge-secret"
    old_serializer = URLSafeTimedSerializer(secret, salt="alpha-knowledge-session-v1")
    token = old_serializer.dumps({"sub": "user-123"})
    codec = SignedSessionCodec(secret, salt="alpha-knowledge-session-v1", max_age_seconds=60)

    assert codec.read_subject(token) == "user-123"
    assert codec.read_subject(codec.issue("user-456")) == "user-456"


def test_shared_codec_rejects_bad_or_subjectless_session():
    codec = SignedSessionCodec("test-only-knowledge-secret", salt="alpha-knowledge-session-v1",
                               max_age_seconds=60)
    serializer = URLSafeTimedSerializer("test-only-knowledge-secret", salt="alpha-knowledge-session-v1")

    with pytest.raises(InvalidSession):
        codec.read_subject("forged")
    with pytest.raises(InvalidSession):
        codec.read_subject(serializer.dumps({"role": "admin"}))


def test_csrf_token_is_signed_time_limited_and_bound_to_session_subject():
    codec = SignedSessionCodec("test-only-knowledge-secret", salt="alpha-knowledge-session-v1",
                               max_age_seconds=60)
    token = codec.issue_csrf("user-123")

    assert codec.verify_csrf(token, "user-123") is None
    with pytest.raises(InvalidCsrfToken):
        codec.verify_csrf(token, "other-user")
    with pytest.raises(InvalidCsrfToken):
        codec.verify_csrf("forged", "user-123")

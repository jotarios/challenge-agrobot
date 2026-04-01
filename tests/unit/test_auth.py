"""Unit tests for JWT authentication."""

import pytest
from datetime import datetime, timedelta, timezone

import jwt

from src.api.deps import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from src.shared.config import settings


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "secure_password_123"
        hashed = hash_password(password)
        assert verify_password(password, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct_password")
        assert not verify_password("wrong_password", hashed)

    def test_hash_is_not_plaintext(self):
        password = "my_password"
        hashed = hash_password(password)
        assert hashed != password


class TestJWT:
    def test_create_and_decode_token(self):
        token = create_access_token(user_id=42, is_admin=False)
        payload = decode_token(token)
        assert payload["sub"] == "42"
        assert payload["is_admin"] is False

    def test_admin_claim(self):
        token = create_access_token(user_id=1, is_admin=True)
        payload = decode_token(token)
        assert payload["is_admin"] is True

    def test_expired_token_raises(self):
        payload = {
            "sub": "42",
            "is_admin": False,
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_invalid_signature_raises(self):
        token = jwt.encode(
            {"sub": "42", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "wrong-secret",
            algorithm="HS256",
        )
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_malformed_token_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            decode_token("not-a-real-token")

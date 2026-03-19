"""
Test Suite: Authentication Module
==================================
Tests for password hashing, JWT token creation/verification.
"""

import time
import pytest
from datetime import timedelta
from jose import jwt

from backend.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    verify_token,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)


# ── Password Hashing ─────────────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_string(self):
        hashed = get_password_hash("mypassword")
        assert hashed.startswith("$2b$")
        assert len(hashed) > 50

    def test_verify_correct_password(self):
        password = "StrongPass@2026"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        hashed = get_password_hash("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_different_hashes_for_same_password(self):
        """bcrypt should produce different salts each time."""
        h1 = get_password_hash("samepass")
        h2 = get_password_hash("samepass")
        assert h1 != h2  # Different salts

    def test_empty_password_still_hashes(self):
        hashed = get_password_hash("")
        assert hashed.startswith("$2b$")


# ── Access Token ──────────────────────────────────────────────────────────────

class TestAccessToken:
    def test_create_access_token_contains_email(self, sample_email):
        token = create_access_token(data={"sub": sample_email})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == sample_email

    def test_access_token_has_type_field(self, sample_email):
        token = create_access_token(data={"sub": sample_email})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["type"] == "access"

    def test_access_token_has_expiry(self, sample_email):
        token = create_access_token(data={"sub": sample_email})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert "exp" in payload

    def test_custom_expiry(self, sample_email):
        token = create_access_token(
            data={"sub": sample_email},
            expires_delta=timedelta(minutes=5),
        )
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert "exp" in payload

    def test_verify_valid_access_token(self, sample_email):
        token = create_access_token(data={"sub": sample_email})
        email = verify_token(token)
        assert email == sample_email

    def test_verify_expired_token_returns_none(self, sample_email):
        token = create_access_token(
            data={"sub": sample_email},
            expires_delta=timedelta(seconds=-1),  # Already expired
        )
        email = verify_token(token)
        assert email is None

    def test_verify_garbage_token_returns_none(self):
        email = verify_token("not.a.valid.token")
        assert email is None

    def test_verify_tampered_token_returns_none(self, sample_email):
        token = create_access_token(data={"sub": sample_email})
        # Tamper with the payload
        tampered = token[:-5] + "XXXXX"
        email = verify_token(tampered)
        assert email is None


# ── Refresh Token ─────────────────────────────────────────────────────────────

class TestRefreshToken:
    def test_create_refresh_token_contains_email(self, sample_email):
        token = create_refresh_token(data={"sub": sample_email})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == sample_email

    def test_refresh_token_type_is_refresh(self, sample_email):
        token = create_refresh_token(data={"sub": sample_email})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["type"] == "refresh"

    def test_verify_valid_refresh_token(self, sample_email):
        token = create_refresh_token(data={"sub": sample_email})
        email = verify_refresh_token(token)
        assert email == sample_email

    def test_verify_access_token_as_refresh_returns_none(self, sample_email):
        """Access tokens should NOT pass refresh token verification."""
        access_token = create_access_token(data={"sub": sample_email})
        result = verify_refresh_token(access_token)
        assert result is None

    def test_verify_garbage_refresh_token(self):
        result = verify_refresh_token("garbage.token.here")
        assert result is None

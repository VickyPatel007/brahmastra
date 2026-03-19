"""
Brahmastra Test Fixtures
=========================
Shared fixtures for all test modules.
"""

import os
import sys
import pytest

# Ensure project root is on sys.path so `backend.*` imports work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Override env vars BEFORE any backend imports ──────────────────────────────
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_brahmastra.db")
os.environ.setdefault("BAN_STATE_FILE", "/tmp/brahmastra_test_bans.json")


# ── Auth fixtures ─────────────────────────────────────────────────────────────
from backend.auth import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
)


@pytest.fixture
def sample_email():
    return "testuser@brahmastra.dev"


@pytest.fixture
def sample_password():
    return "SuperSecure@123"


@pytest.fixture
def sample_hashed_password(sample_password):
    return get_password_hash(sample_password)


@pytest.fixture
def valid_access_token(sample_email):
    """Create a valid JWT access token for testing."""
    return create_access_token(data={"sub": sample_email})


@pytest.fixture
def valid_refresh_token(sample_email):
    """Create a valid JWT refresh token for testing."""
    return create_refresh_token(data={"sub": sample_email})


# ── Threat Detection fixtures ────────────────────────────────────────────────
@pytest.fixture
def fresh_threat_engine():
    """Create a fresh ThreatDetectionEngine instance for isolated tests."""
    from backend.threat_detection import ThreatDetectionEngine
    engine = ThreatDetectionEngine()
    return engine


# ── Rate Limiter fixtures ────────────────────────────────────────────────────
@pytest.fixture
def fresh_rate_limiter():
    """Create a fresh SlidingWindowRateLimiter instance for isolated tests."""
    from backend.rate_limiter import SlidingWindowRateLimiter
    limiter = SlidingWindowRateLimiter()
    return limiter


# ── Cleanup ──────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def cleanup_ban_file():
    """Remove test ban state file after each test."""
    yield
    ban_file = os.environ.get("BAN_STATE_FILE", "/tmp/brahmastra_test_bans.json")
    if os.path.exists(ban_file):
        os.remove(ban_file)

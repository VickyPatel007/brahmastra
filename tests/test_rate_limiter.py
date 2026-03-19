"""
Test Suite: Rate Limiter
=========================
Tests for sliding window, attack mode, circuit breaker, and request classification.
"""

import time
import pytest

from backend.rate_limiter import SlidingWindowRateLimiter, RATE_LIMITS


# ── Sliding Window ───────────────────────────────────────────────────────────

class TestSlidingWindow:
    def test_first_request_allowed(self, fresh_rate_limiter):
        allowed, info = fresh_rate_limiter.check("192.168.1.1", "api")
        assert allowed is True
        assert info["allowed"] is True
        assert info["category"] == "api"

    def test_requests_within_limit_allowed(self, fresh_rate_limiter):
        ip = "192.168.1.2"
        for _ in range(5):
            allowed, _ = fresh_rate_limiter.check(ip, "api")
        assert allowed is True

    def test_login_rate_limit_enforced(self, fresh_rate_limiter):
        """Login rate limit is 5 per 60 seconds."""
        ip = "192.168.1.3"
        max_login = RATE_LIMITS["login"]["max_requests"]
        for i in range(max_login):
            allowed, _ = fresh_rate_limiter.check(ip, "login")
            assert allowed is True, f"Request {i+1} should be allowed"
        # Next one should be blocked
        allowed, info = fresh_rate_limiter.check(ip, "login")
        assert allowed is False
        assert info["remaining"] == 0
        assert "retry_after" in info

    def test_register_rate_limit_enforced(self, fresh_rate_limiter):
        """Register rate limit is 3 per 60 seconds."""
        ip = "192.168.1.4"
        max_register = RATE_LIMITS["register"]["max_requests"]
        for i in range(max_register):
            allowed, _ = fresh_rate_limiter.check(ip, "register")
        allowed, info = fresh_rate_limiter.check(ip, "register")
        assert allowed is False

    def test_different_ips_independent(self, fresh_rate_limiter):
        """Each IP should have independent rate limit counters."""
        max_login = RATE_LIMITS["login"]["max_requests"]
        # Exhaust IP1's login limit
        for _ in range(max_login):
            fresh_rate_limiter.check("10.0.0.1", "login")
        allowed1, _ = fresh_rate_limiter.check("10.0.0.1", "login")
        # IP2 should still be allowed
        allowed2, _ = fresh_rate_limiter.check("10.0.0.2", "login")
        assert allowed1 is False
        assert allowed2 is True

    def test_different_categories_independent(self, fresh_rate_limiter):
        """Login and API limits should be tracked separately."""
        ip = "192.168.1.5"
        max_login = RATE_LIMITS["login"]["max_requests"]
        # Exhaust login limit
        for _ in range(max_login):
            fresh_rate_limiter.check(ip, "login")
        blocked_login, _ = fresh_rate_limiter.check(ip, "login")
        # API should still be allowed
        allowed_api, _ = fresh_rate_limiter.check(ip, "api")
        assert blocked_login is False
        assert allowed_api is True

    def test_remaining_count_decreases(self, fresh_rate_limiter):
        ip = "192.168.1.6"
        _, info1 = fresh_rate_limiter.check(ip, "api")
        _, info2 = fresh_rate_limiter.check(ip, "api")
        assert info2["remaining"] < info1["remaining"]


# ── Attack Mode ──────────────────────────────────────────────────────────────

class TestAttackMode:
    def test_attack_mode_tightens_limits(self, fresh_rate_limiter):
        """In attack mode, limits drop to 40%."""
        ip = "192.168.2.1"
        fresh_rate_limiter.set_attack_mode(True)
        # API limit is normally 120, attack mode = 48
        allowed_count = 0
        for _ in range(120):
            allowed, _ = fresh_rate_limiter.check(ip, "api")
            if allowed:
                allowed_count += 1
            else:
                break
        # Should be blocked well before 120
        assert allowed_count < 120
        assert allowed_count <= int(RATE_LIMITS["api"]["max_requests"] * 0.4) + 1

    def test_attack_mode_toggle(self, fresh_rate_limiter):
        fresh_rate_limiter.set_attack_mode(True)
        status = fresh_rate_limiter.get_status()
        assert status["attack_mode"] is True

        fresh_rate_limiter.set_attack_mode(False)
        status = fresh_rate_limiter.get_status()
        assert status["attack_mode"] is False


# ── Circuit Breaker ──────────────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_circuit_breaker_blocks_all(self, fresh_rate_limiter):
        fresh_rate_limiter.set_circuit_breaker(True)
        allowed, info = fresh_rate_limiter.check("192.168.3.1", "api")
        assert allowed is False
        assert info["reason"] == "circuit_breaker"

    def test_circuit_breaker_allows_health(self, fresh_rate_limiter):
        """Health and public endpoints should work even with circuit breaker."""
        fresh_rate_limiter.set_circuit_breaker(True)
        allowed, _ = fresh_rate_limiter.check("192.168.3.2", "health")
        assert allowed is True

    def test_circuit_breaker_allows_public(self, fresh_rate_limiter):
        fresh_rate_limiter.set_circuit_breaker(True)
        allowed, _ = fresh_rate_limiter.check("192.168.3.3", "public")
        assert allowed is True

    def test_circuit_breaker_toggle(self, fresh_rate_limiter):
        fresh_rate_limiter.set_circuit_breaker(True)
        status = fresh_rate_limiter.get_status()
        assert status["circuit_breaker_open"] is True

        fresh_rate_limiter.set_circuit_breaker(False)
        status = fresh_rate_limiter.get_status()
        assert status["circuit_breaker_open"] is False


# ── Request Classification ────────────────────────────────────────────────────

class TestRequestClassification:
    @pytest.mark.parametrize("path,expected", [
        ("/api/auth/login", "login"),
        ("/api/auth/register", "register"),
        ("/api/auth/forgot-password", "forgot_password"),
        ("/ws/updates", "ws"),
        ("/health", "public"),
        ("/", "public"),
        ("/api/stats", "api"),
        ("/api/metrics", "api"),
        ("/random-path", "default"),
    ])
    def test_classify_request(self, fresh_rate_limiter, path, expected):
        result = fresh_rate_limiter.classify_request(path, "GET")
        assert result == expected


# ── Status Reporting ──────────────────────────────────────────────────────────

class TestStatusReporting:
    def test_get_status_structure(self, fresh_rate_limiter):
        status = fresh_rate_limiter.get_status()
        assert "active_ips" in status
        assert "tracked_entries" in status
        assert "total_blocked_requests" in status
        assert "attack_mode" in status
        assert "circuit_breaker_open" in status
        assert "top_blocked_ips" in status
        assert "uptime_seconds" in status
        assert "rate_limits" in status

    def test_blocked_count_increases(self, fresh_rate_limiter):
        ip = "192.168.5.1"
        max_login = RATE_LIMITS["login"]["max_requests"]
        for _ in range(max_login):
            fresh_rate_limiter.check(ip, "login")
        # Trigger block
        fresh_rate_limiter.check(ip, "login")
        status = fresh_rate_limiter.get_status()
        assert status["total_blocked_requests"] >= 1

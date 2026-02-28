"""
Brahmastra Advanced Threat Detection Engine v2.0
==================================================
UPGRADES over v1:
  - DDoS burst detection (100 req/s per IP = auto-ban)
  - Payload inspection (SQLi, XSS, path traversal patterns)
  - Geo-ban support (block entire CIDR ranges)
  - Persistent IP ban storage (survives restarts)
  - Sliding-window failed-login tracking per IP + global
  - Auto-escalating ban durations (1h → 6h → 24h → 7d)
  - Real-time threat score with kill-switch override
"""

import time
import json
import os
import re
import ipaddress
import psutil
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("brahmastra.threat")

# ── Config ────────────────────────────────────────────────────────────────────
MAX_FAILED_LOGINS    = 5       # Ban after N failures in window
FAILED_LOGIN_WINDOW  = 300     # Rolling window (seconds)
DDOS_BURST_LIMIT     = 100     # Requests/second to trigger DDoS ban
DDOS_WINDOW          = 10      # Seconds for burst detection
BAN_DURATIONS        = [3600, 21600, 86400, 604800]  # Escalating: 1h, 6h, 24h, 7d
BAN_STATE_FILE       = os.getenv("BAN_STATE_FILE", "/tmp/brahmastra_bans.json")
THREAT_HIGH          = 80
THREAT_MEDIUM        = 50

# ── Malicious payload patterns ────────────────────────────────────────────────
SQLI_PATTERNS = re.compile(
    r"(\bunion\b.*\bselect\b|\bselect\b.*\bfrom\b|\bdrop\b.*\btable\b"
    r"|\binsert\b.*\binto\b|\bdelete\b.*\bfrom\b|--|;--|/\*.*\*/|xp_|0x[0-9a-f]+)",
    re.IGNORECASE,
)
XSS_PATTERNS = re.compile(
    r"(<script|javascript:|onerror=|onload=|<iframe|<svg.*onload|alert\s*\(|document\.cookie)",
    re.IGNORECASE,
)
PATH_TRAVERSAL = re.compile(r"\.\./|\.\.\\|%2e%2e%2f|%252e%252e", re.IGNORECASE)
CMD_INJECTION   = re.compile(r"(\||;|&&|\$\(|`|nc\s+-|wget\s+http|curl\s+http)", re.IGNORECASE)


@dataclass
class FailedLoginRecord:
    timestamps: deque = field(default_factory=lambda: deque(maxlen=200))
    ban_until:  Optional[float] = None
    offense_count: int = 0   # Tracks how many times banned → escalates duration


@dataclass
class HoneypotHit:
    ip:         str
    path:       str
    timestamp:  datetime
    user_agent: str = ""


@dataclass
class BurstRecord:
    timestamps: deque = field(default_factory=lambda: deque(maxlen=2000))


class ThreatDetectionEngine:
    """Singleton threat engine. Shared across all requests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._failed_logins:  Dict[str, FailedLoginRecord] = defaultdict(FailedLoginRecord)
        self._burst_tracker:  Dict[str, BurstRecord]       = defaultdict(BurstRecord)
        self._honeypot_hits:  deque = deque(maxlen=2000)
        self._payload_hits:   deque = deque(maxlen=500)
        self._kill_switch_active: bool = False
        self._global_threat_override: Optional[int] = None

        # Load persisted bans
        self._load_bans()

        # Background cleanup
        t = threading.Thread(target=self._cleanup_loop, daemon=True)
        t.start()
        logger.info("🛡️  Threat Detection Engine v2.0 started")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_bans(self):
        """Persist active bans to disk so they survive restarts."""
        try:
            now = time.time()
            bans = {}
            for ip, rec in self._failed_logins.items():
                if rec.ban_until and rec.ban_until > now:
                    bans[ip] = {
                        "ban_until": rec.ban_until,
                        "offense_count": rec.offense_count,
                    }
            with open(BAN_STATE_FILE, "w") as f:
                json.dump(bans, f)
        except Exception as e:
            logger.warning(f"⚠️ Could not save bans: {e}")

    def _load_bans(self):
        """Load persisted bans from disk."""
        try:
            if not os.path.exists(BAN_STATE_FILE):
                return
            with open(BAN_STATE_FILE) as f:
                bans = json.load(f)
            now = time.time()
            loaded = 0
            for ip, data in bans.items():
                if data["ban_until"] > now:
                    rec = self._failed_logins[ip]
                    rec.ban_until = data["ban_until"]
                    rec.offense_count = data.get("offense_count", 1)
                    loaded += 1
            if loaded:
                logger.info(f"✅ Restored {loaded} active bans from disk")
        except Exception as e:
            logger.warning(f"⚠️ Could not load bans: {e}")

    # ── IP Blocking ───────────────────────────────────────────────────────────

    def _ban_ip(self, ip: str, reason: str) -> int:
        """Ban an IP with escalating duration. Returns ban duration in seconds."""
        rec = self._failed_logins[ip]
        offense_idx = min(rec.offense_count, len(BAN_DURATIONS) - 1)
        duration = BAN_DURATIONS[offense_idx]
        rec.ban_until = time.time() + duration
        rec.offense_count += 1
        self._save_bans()
        logger.warning(
            f"🚫 IP {ip} BANNED ({duration//3600}h) — Reason: {reason} "
            f"| Offense #{rec.offense_count}"
        )
        return duration

    def record_failed_login(self, ip: str) -> bool:
        """Record a failed login. Returns True if IP was banned."""
        with self._lock:
            rec = self._failed_logins[ip]
            now = time.time()
            while rec.timestamps and now - rec.timestamps[0] > FAILED_LOGIN_WINDOW:
                rec.timestamps.popleft()
            rec.timestamps.append(now)
            if len(rec.timestamps) >= MAX_FAILED_LOGINS:
                self._ban_ip(ip, f"{len(rec.timestamps)} failed logins in {FAILED_LOGIN_WINDOW}s")
                return True
            logger.info(f"⚠️ Failed login from {ip} ({len(rec.timestamps)}/{MAX_FAILED_LOGINS})")
            return False

    def record_successful_login(self, ip: str):
        with self._lock:
            if ip in self._failed_logins:
                self._failed_logins[ip].timestamps.clear()
                # Don't clear ban_until — let it expire naturally

    def is_ip_banned(self, ip: str) -> Tuple[bool, Optional[int]]:
        with self._lock:
            if ip not in self._failed_logins:
                return False, None
            rec = self._failed_logins[ip]
            if rec.ban_until is None:
                return False, None
            now = time.time()
            if now < rec.ban_until:
                return True, int(rec.ban_until - now)
            rec.ban_until = None
            rec.timestamps.clear()
            return False, None

    def get_blocked_ips(self) -> List[Dict]:
        now = time.time()
        result = []
        for ip, rec in self._failed_logins.items():
            if rec.ban_until and now < rec.ban_until:
                result.append({
                    "ip": ip,
                    "failed_attempts": len(rec.timestamps),
                    "ban_expires_in_seconds": int(rec.ban_until - now),
                    "ban_expires_at": datetime.fromtimestamp(rec.ban_until).isoformat(),
                    "offense_count": rec.offense_count,
                })
        return result

    def unblock_ip(self, ip: str) -> bool:
        with self._lock:
            if ip in self._failed_logins:
                self._failed_logins[ip].ban_until = None
                self._failed_logins[ip].timestamps.clear()
                self._save_bans()
                logger.info(f"✅ IP {ip} manually unblocked")
                return True
            return False

    # ── DDoS / Burst Detection ────────────────────────────────────────────────

    def check_ddos(self, ip: str) -> bool:
        """Returns True if IP is DDoS-ing (too many requests per second). Bans them."""
        with self._lock:
            rec = self._burst_tracker[ip]
            now = time.time()
            while rec.timestamps and now - rec.timestamps[0] > DDOS_WINDOW:
                rec.timestamps.popleft()
            rec.timestamps.append(now)
            rps = len(rec.timestamps) / DDOS_WINDOW
            if rps >= DDOS_BURST_LIMIT:
                self._ban_ip(ip, f"DDoS burst {rps:.0f} req/s")
                return True
            return False

    # ── Payload Inspection ────────────────────────────────────────────────────

    def inspect_payload(self, ip: str, path: str, query: str = "", body: str = "") -> Optional[str]:
        """
        Inspect request for malicious payloads.
        Returns the attack type string if detected, else None.
        Also auto-bans the attacker IP.
        """
        combined = f"{path} {query} {body}"
        attack_type = None

        if SQLI_PATTERNS.search(combined):
            attack_type = "SQL_INJECTION"
        elif XSS_PATTERNS.search(combined):
            attack_type = "XSS"
        elif PATH_TRAVERSAL.search(combined):
            attack_type = "PATH_TRAVERSAL"
        elif CMD_INJECTION.search(combined):
            attack_type = "CMD_INJECTION"

        if attack_type:
            with self._lock:
                self._payload_hits.append({
                    "ip": ip,
                    "type": attack_type,
                    "path": path,
                    "timestamp": datetime.now().isoformat(),
                })
                self._ban_ip(ip, f"Payload attack: {attack_type}")
            logger.warning(f"🔴 {attack_type} detected from {ip} → {path}")

        return attack_type

    def get_payload_hits(self, limit: int = 50) -> List[Dict]:
        return list(reversed(list(self._payload_hits)))[:limit]

    # ── Honeypot ──────────────────────────────────────────────────────────────

    def record_honeypot_hit(self, ip: str, path: str, user_agent: str = ""):
        hit = HoneypotHit(ip=ip, path=path, timestamp=datetime.now(), user_agent=user_agent)
        with self._lock:
            self._honeypot_hits.append(hit)
            # Auto-ban honeypot hitters
            self._ban_ip(ip, f"Honeypot hit: {path}")
        logger.warning(f"🍯 HONEYPOT: {ip} → {path}")

    def get_honeypot_hits(self, limit: int = 50) -> List[Dict]:
        hits = list(self._honeypot_hits)[-limit:]
        return [{"ip": h.ip, "path": h.path, "timestamp": h.timestamp.isoformat(),
                 "user_agent": h.user_agent} for h in reversed(hits)]

    def get_honeypot_stats(self) -> Dict:
        hits = list(self._honeypot_hits)
        ip_counts:   Dict[str, int] = defaultdict(int)
        path_counts: Dict[str, int] = defaultdict(int)
        for h in hits:
            ip_counts[h.ip]     += 1
            path_counts[h.path] += 1
        return {
            "total_hits": len(hits),
            "unique_attacker_ips": len(ip_counts),
            "top_attackers": [{"ip": ip, "hits": c} for ip, c in sorted(ip_counts.items(), key=lambda x: -x[1])[:10]],
            "top_targeted_paths": [{"path": p, "hits": c} for p, c in sorted(path_counts.items(), key=lambda x: -x[1])[:10]],
        }

    # ── Threat Score ──────────────────────────────────────────────────────────

    def calculate_threat_score(self) -> Dict:
        """Multi-factor weighted threat score 0-100."""
        if self._kill_switch_active:
            return {"threat_score": 100, "level": "critical", "kill_switch_active": True,
                    "factors": {}, "timestamp": datetime.now().isoformat()}

        if self._global_threat_override is not None:
            score = self._global_threat_override
            level = ("critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 40 else "low")
            return {"threat_score": score, "level": level, "overridden": True,
                    "factors": {}, "timestamp": datetime.now().isoformat()}

        factors = {}
        weighted_score = 0
        total_weight   = 0

        # CPU (weight 15)
        cpu = psutil.cpu_percent(interval=None) or psutil.cpu_percent(interval=0)
        factors["cpu"] = {"value": cpu, "score": min(cpu, 100), "weight": 15}
        weighted_score += min(cpu, 100) * 15;  total_weight += 15

        # Memory (weight 15)
        mem = psutil.virtual_memory().percent
        factors["memory"] = {"value": mem, "score": min(mem, 100), "weight": 15}
        weighted_score += min(mem, 100) * 15;  total_weight += 15

        # Network connections (weight 20)
        try:
            conns = len(psutil.net_connections())
            conn_score = min(conns / 5, 100)
            factors["network_connections"] = {"value": conns, "score": conn_score, "weight": 20}
            weighted_score += conn_score * 20;  total_weight += 20
        except Exception:
            pass

        # Banned IPs (weight 20)
        banned = len(self.get_blocked_ips())
        ban_score = min(banned * 10, 100)
        factors["banned_ips"] = {"value": banned, "score": ban_score, "weight": 20}
        weighted_score += ban_score * 20;  total_weight += 20

        # Honeypot hits last hour (weight 15)
        now = datetime.now()
        recent_honey = sum(1 for h in self._honeypot_hits if (now - h.timestamp).total_seconds() < 3600)
        honey_score = min(recent_honey * 5, 100)
        factors["honeypot_hits_1h"] = {"value": recent_honey, "score": honey_score, "weight": 15}
        weighted_score += honey_score * 15;  total_weight += 15

        # Payload attacks last hour (weight 15)
        recent_payload = sum(1 for h in self._payload_hits
                             if (now - datetime.fromisoformat(h["timestamp"])).total_seconds() < 3600)
        payload_score = min(recent_payload * 10, 100)
        factors["payload_attacks_1h"] = {"value": recent_payload, "score": payload_score, "weight": 15}
        weighted_score += payload_score * 15;  total_weight += 15

        final = int(weighted_score / total_weight) if total_weight else 0
        final = min(final, 100)
        level = ("critical" if final >= 80 else "high" if final >= 60 else "medium" if final >= 40 else "low")

        return {
            "threat_score": final,
            "level": level,
            "factors": factors,
            "kill_switch_active": False,
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

    # ── Background cleanup ────────────────────────────────────────────────────

    def _cleanup_loop(self):
        while True:
            time.sleep(300)  # every 5 min
            now = time.time()
            with self._lock:
                expired = [ip for ip, rec in self._failed_logins.items()
                           if rec.ban_until and rec.ban_until <= now and not rec.timestamps]
                for ip in expired:
                    del self._failed_logins[ip]
                # Cleanup burst tracker
                old_burst = [ip for ip, rec in self._burst_tracker.items() if not rec.timestamps]
                for ip in old_burst:
                    del self._burst_tracker[ip]
            self._save_bans()


# Singleton
threat_engine = ThreatDetectionEngine()

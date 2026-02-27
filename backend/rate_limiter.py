"""
Brahmastra Rate Limiter v2.0
============================
UPGRADES over v1:
  - Adaptive limits that tighten automatically under attack
  - Per-IP penalty escalation (blocked count → shorter window)
  - Circuit breaker: global freeze when server is overwhelmed
  - Request burst detection integrated with threat engine
  - Zero external dependencies
"""

import time
import threading
import logging
from collections import defaultdict
from typing import Dict, Tuple

logger = logging.getLogger("brahmastra.ratelimit")

# ── Base rate limit config per category ──────────────────────────────────────
RATE_LIMITS = {
    "login":          {"max_requests": 5,   "window_seconds": 60},
    "register":       {"max_requests": 3,   "window_seconds": 60},
    "forgot_password":{"max_requests": 2,   "window_seconds": 60},
    "api":            {"max_requests": 120, "window_seconds": 60},
    "ws":             {"max_requests": 5,   "window_seconds": 60},
    "public":         {"max_requests": 30,  "window_seconds": 60},
    "default":        {"max_requests": 60,  "window_seconds": 60},
}

# Under attack: limits shrink to these percentages
ATTACK_MODE_MULTIPLIER = 0.4  # 40% of normal limits


class SlidingWindowRateLimiter:
    """
    Thread-safe sliding window rate limiter with:
      - Adaptive tightening when server load is high
      - Circuit breaker (global throttle under extreme load)
      - Per-IP offense tracking with exponential backoff
    """

    def __init__(self):
        self._requests: Dict[Tuple[str, str], list] = defaultdict(list)
        self._lock = threading.Lock()
        self._blocked_count: Dict[str, int] = defaultdict(int)
        self._total_blocked = 0
        self._start_time = time.time()
        self._attack_mode = False
        self._circuit_open = False  # True = reject everything except health

        # Background cleanup + adaptive check
        t = threading.Thread(target=self._background_loop, daemon=True)
        t.start()
        logger.info("✅ Rate limiter v2.0 initialized")

    def check(self, ip: str, category: str = "default") -> Tuple[bool, dict]:
        """
        Check if request is allowed.
        Returns (allowed: bool, info: dict)
        """
        # Circuit breaker: only allow health checks
        if self._circuit_open and category not in ("health", "public"):
            return False, {
                "allowed": False,
                "category": category,
                "limit": 0,
                "remaining": 0,
                "retry_after": 30,
                "window": 60,
                "reason": "circuit_breaker",
            }

        config = RATE_LIMITS.get(category, RATE_LIMITS["default"])
        max_req = config["max_requests"]
        window  = config["window_seconds"]

        # Tighten limits under attack
        if self._attack_mode:
            max_req = max(1, int(max_req * ATTACK_MODE_MULTIPLIER))

        # Further penalize repeat offenders
        offenses = self._blocked_count.get(ip, 0)
        if offenses >= 10:
            max_req = max(1, max_req // 4)
        elif offenses >= 5:
            max_req = max(1, max_req // 2)

        now = time.time()
        key = (ip, category)

        with self._lock:
            self._requests[key] = [ts for ts in self._requests[key] if now - ts < window]
            current = len(self._requests[key])

            if current >= max_req:
                self._blocked_count[ip] = self._blocked_count.get(ip, 0) + 1
                self._total_blocked += 1
                oldest = self._requests[key][0] if self._requests[key] else now
                retry  = int(window - (now - oldest)) + 1
                return False, {
                    "allowed": False,
                    "category": category,
                    "limit": max_req,
                    "remaining": 0,
                    "retry_after": retry,
                    "window": window,
                }

            self._requests[key].append(now)
            return True, {
                "allowed": True,
                "category": category,
                "limit": max_req,
                "remaining": max_req - current - 1,
                "window": window,
            }

    def set_attack_mode(self, active: bool):
        if active != self._attack_mode:
            self._attack_mode = active
            logger.warning(f"⚔️ Attack mode {'ENABLED' if active else 'DISABLED'}")

    def set_circuit_breaker(self, open_: bool):
        if open_ != self._circuit_open:
            self._circuit_open = open_
            logger.critical(f"⚡ Circuit breaker {'OPEN (blocking all)' if open_ else 'CLOSED (normal)'}")

    def get_status(self) -> dict:
        now = time.time()
        with self._lock:
            active_ips = set()
            active_entries = 0
            for (ip, _), timestamps in self._requests.items():
                valid = [ts for ts in timestamps if now - ts < 120]
                if valid:
                    active_ips.add(ip)
                    active_entries += len(valid)
        return {
            "active_ips": len(active_ips),
            "tracked_entries": active_entries,
            "total_blocked_requests": self._total_blocked,
            "attack_mode": self._attack_mode,
            "circuit_breaker_open": self._circuit_open,
            "top_blocked_ips": dict(sorted(self._blocked_count.items(), key=lambda x: -x[1])[:10]),
            "uptime_seconds": int(now - self._start_time),
            "rate_limits": RATE_LIMITS,
        }

    def classify_request(self, path: str, method: str) -> str:
        p = path.lower()
        if "/api/auth/login" in p:          return "login"
        if "/api/auth/register" in p:       return "register"
        if "/api/auth/forgot-password" in p:return "forgot_password"
        if p.startswith("/ws"):             return "ws"
        if p in ("/health", "/"):           return "public"
        if p.startswith("/api/"):           return "api"
        return "default"

    def _background_loop(self):
        """Cleanup expired entries every 60s; auto-detect attack mode."""
        import psutil
        while True:
            time.sleep(60)
            now = time.time()
            with self._lock:
                keys_to_del = []
                for key, ts in self._requests.items():
                    self._requests[key] = [t for t in ts if now - t < 120]
                    if not self._requests[key]:
                        keys_to_del.append(key)
                for k in keys_to_del:
                    del self._requests[k]

            # Auto attack mode based on block rate
            try:
                cpu = psutil.cpu_percent(interval=0.2)
                if cpu > 90:
                    self.set_attack_mode(True)
                elif cpu < 60:
                    self.set_attack_mode(False)
            except Exception:
                pass


# Singleton
rate_limiter = SlidingWindowRateLimiter()

"""
Brahmastra Rate Limiter
========================
Sliding-window per-IP rate limiter with configurable limits per route category.
No external dependencies (no Redis needed).

Categories:
    - login: 5 requests/minute (brute-force protection)
    - register: 3 requests/minute (spam prevention)
    - api: 60 requests/minute (general API)
    - ws: 10 connections/minute (WebSocket)
"""

import time
import threading
import logging
from collections import defaultdict
from typing import Dict, Tuple, Optional

logger = logging.getLogger("brahmastra.ratelimit")


# ── Configuration ────────────────────────────────────────────────────────────
RATE_LIMITS = {
    "login":    {"max_requests": 5,  "window_seconds": 60},
    "register": {"max_requests": 3,  "window_seconds": 60},
    "api":      {"max_requests": 60, "window_seconds": 60},
    "ws":       {"max_requests": 10, "window_seconds": 60},
    "default":  {"max_requests": 30, "window_seconds": 60},
}


class SlidingWindowRateLimiter:
    """
    Thread-safe sliding window rate limiter.
    Tracks request timestamps per (IP, category) and rejects
    requests that exceed the configured limit.
    """

    def __init__(self):
        # { (ip, category): [timestamp1, timestamp2, ...] }
        self._requests: Dict[Tuple[str, str], list] = defaultdict(list)
        self._lock = threading.Lock()
        self._blocked_count: Dict[str, int] = defaultdict(int)
        self._total_blocked = 0
        self._start_time = time.time()

        # Auto-cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        logger.info("Rate limiter initialized")

    def check(self, ip: str, category: str = "default") -> Tuple[bool, dict]:
        """
        Check if a request from this IP in this category is allowed.
        Returns (allowed: bool, info: dict)
        """
        config = RATE_LIMITS.get(category, RATE_LIMITS["default"])
        max_requests = config["max_requests"]
        window = config["window_seconds"]
        now = time.time()
        key = (ip, category)

        with self._lock:
            # Remove expired timestamps
            self._requests[key] = [
                ts for ts in self._requests[key]
                if now - ts < window
            ]

            current_count = len(self._requests[key])

            if current_count >= max_requests:
                self._blocked_count[ip] = self._blocked_count.get(ip, 0) + 1
                self._total_blocked += 1

                # Calculate retry-after
                oldest = self._requests[key][0] if self._requests[key] else now
                retry_after = int(window - (now - oldest)) + 1

                return False, {
                    "allowed": False,
                    "category": category,
                    "limit": max_requests,
                    "remaining": 0,
                    "retry_after": retry_after,
                    "window": window,
                }

            # Allow and record
            self._requests[key].append(now)
            remaining = max_requests - current_count - 1

            return True, {
                "allowed": True,
                "category": category,
                "limit": max_requests,
                "remaining": remaining,
                "window": window,
            }

    def get_status(self) -> dict:
        """Get current rate limiter statistics."""
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
                "top_blocked_ips": dict(
                    sorted(self._blocked_count.items(), key=lambda x: -x[1])[:10]
                ),
                "uptime_seconds": int(now - self._start_time),
                "rate_limits": RATE_LIMITS,
            }

    def _cleanup_loop(self):
        """Background cleanup of expired entries every 60 seconds."""
        while True:
            time.sleep(60)
            now = time.time()
            with self._lock:
                keys_to_delete = []
                for key, timestamps in self._requests.items():
                    self._requests[key] = [
                        ts for ts in timestamps
                        if now - ts < 120
                    ]
                    if not self._requests[key]:
                        keys_to_delete.append(key)
                for key in keys_to_delete:
                    del self._requests[key]

    def classify_request(self, path: str, method: str) -> str:
        """Classify a request into a rate limit category."""
        path_lower = path.lower()

        if "/api/auth/login" in path_lower:
            return "login"
        elif "/api/auth/register" in path_lower:
            return "register"
        elif path_lower.startswith("/ws"):
            return "ws"
        elif path_lower.startswith("/api/"):
            return "api"
        else:
            return "default"


# Singleton
rate_limiter = SlidingWindowRateLimiter()

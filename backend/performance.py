"""
Brahmastra Performance Tracker
================================
Tracks API response times, request counts, error rates, and uptime.
Provides p50/p95/p99 latency metrics and identifies slow endpoints.

Features:
    - Per-endpoint response time tracking
    - Rolling window stats (last 1000 requests)
    - Uptime tracking
    - Error rate calculation
    - Slowest endpoint identification
"""

import time
import threading
import logging
from collections import defaultdict, deque
from typing import Dict, List

logger = logging.getLogger("brahmastra.performance")

# Keep last N requests for stats
MAX_HISTORY = 1000


class PerformanceTracker:
    """Tracks and reports API performance metrics."""

    def __init__(self):
        self._start_time = time.time()
        self._lock = threading.Lock()

        # Per-endpoint stats
        # { endpoint: deque([(timestamp, duration_ms, status_code), ...]) }
        self._requests: Dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_HISTORY))

        # Global counters
        self._total_requests = 0
        self._total_errors = 0  # 4xx and 5xx
        self._total_response_time_ms = 0

        # Recent request log for real-time view
        self._recent: deque = deque(maxlen=100)

        logger.info("Performance tracker initialized")

    def record(self, method: str, path: str, status_code: int, duration_ms: float):
        """Record a completed request."""
        # Normalize path (remove query strings, IDs)
        endpoint = self._normalize_path(method, path)
        now = time.time()

        with self._lock:
            self._requests[endpoint].append((now, duration_ms, status_code))
            self._total_requests += 1
            self._total_response_time_ms += duration_ms

            if status_code >= 400:
                self._total_errors += 1

            self._recent.appendleft({
                "endpoint": endpoint,
                "status": status_code,
                "duration_ms": round(duration_ms, 2),
                "timestamp": now,
            })

    def get_stats(self) -> dict:
        """Get comprehensive performance statistics."""
        now = time.time()
        uptime = now - self._start_time

        with self._lock:
            # Calculate per-endpoint stats
            endpoint_stats = {}
            all_durations = []

            for endpoint, entries in self._requests.items():
                # Only consider last 5 minutes for "active" stats
                recent = [(ts, dur, sc) for ts, dur, sc in entries if now - ts < 300]
                durations = [dur for _, dur, _ in recent]
                errors = sum(1 for _, _, sc in recent if sc >= 400)

                if durations:
                    durations_sorted = sorted(durations)
                    n = len(durations_sorted)
                    endpoint_stats[endpoint] = {
                        "count": len(recent),
                        "avg_ms": round(sum(durations) / len(durations), 2),
                        "min_ms": round(min(durations), 2),
                        "max_ms": round(max(durations), 2),
                        "p50_ms": round(durations_sorted[n // 2], 2),
                        "p95_ms": round(durations_sorted[int(n * 0.95)], 2) if n >= 20 else round(max(durations), 2),
                        "p99_ms": round(durations_sorted[int(n * 0.99)], 2) if n >= 100 else round(max(durations), 2),
                        "errors": errors,
                        "error_rate": round(errors / len(recent) * 100, 1) if recent else 0,
                    }
                    all_durations.extend(durations)

            # Global stats
            if all_durations:
                all_sorted = sorted(all_durations)
                n = len(all_sorted)
                global_latency = {
                    "avg_ms": round(sum(all_durations) / n, 2),
                    "p50_ms": round(all_sorted[n // 2], 2),
                    "p95_ms": round(all_sorted[int(n * 0.95)], 2) if n >= 20 else round(max(all_durations), 2),
                    "p99_ms": round(all_sorted[int(n * 0.99)], 2) if n >= 100 else round(max(all_durations), 2),
                }
            else:
                global_latency = {"avg_ms": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0}

            # Requests per second (last 60s)
            recent_60s = sum(
                1 for entries in self._requests.values()
                for ts, _, _ in entries if now - ts < 60
            )
            rps = round(recent_60s / 60, 2)

            return {
                "uptime_seconds": int(uptime),
                "uptime_formatted": self._format_uptime(uptime),
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "error_rate_percent": round(
                    self._total_errors / self._total_requests * 100, 2
                ) if self._total_requests > 0 else 0,
                "requests_per_second": rps,
                "global_latency": global_latency,
                "endpoints": endpoint_stats,
                "active_endpoints": len(endpoint_stats),
            }

    def get_slow_endpoints(self, threshold_ms: float = 100) -> List[dict]:
        """Get endpoints with average response time above threshold."""
        stats = self.get_stats()
        slow = []
        for endpoint, data in stats.get("endpoints", {}).items():
            if data["avg_ms"] > threshold_ms:
                slow.append({"endpoint": endpoint, **data})
        return sorted(slow, key=lambda x: -x["avg_ms"])

    def get_recent_requests(self) -> List[dict]:
        """Get recent requests for real-time monitoring."""
        with self._lock:
            return list(self._recent)[:50]

    @staticmethod
    def _normalize_path(method: str, path: str) -> str:
        """Normalize API paths for grouping."""
        # Remove query params
        path = path.split("?")[0]

        # Replace dynamic segments (UUIDs, IDs)
        parts = path.split("/")
        normalized = []
        for part in parts:
            if len(part) > 20 and "-" in part:
                normalized.append("{id}")
            elif part.isdigit():
                normalized.append("{id}")
            else:
                normalized.append(part)

        return f"{method} {'/'.join(normalized)}"

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """Format uptime as human-readable string."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"


# Singleton
perf_tracker = PerformanceTracker()

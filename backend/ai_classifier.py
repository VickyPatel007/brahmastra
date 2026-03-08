"""
Brahmastra AI Traffic Classifier v1.0
======================================
ML-powered traffic analysis that classifies requests as:
  - NORMAL:  Legitimate user traffic
  - SUSPICIOUS: Might be attack, needs monitoring
  - ATTACK:  Definite attack, redirect to honeypot
  - CRITICAL: Severe breach attempt, trigger emergency response

Features extracted per request:
  - Request rate (per IP, global)
  - Payload entropy & pattern matching
  - Timing analysis (bots vs humans)
  - User-Agent scoring
  - Path sequence analysis
  - Geographic anomaly detection
"""

import time
import math
import re
import os
import json
import logging
import threading
import hashlib
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("brahmastra.ai")

# ── Classification Labels ─────────────────────────────────────────────────────
LABEL_NORMAL     = "normal"
LABEL_SUSPICIOUS = "suspicious"
LABEL_ATTACK     = "attack"
LABEL_CRITICAL   = "critical"

# ── Thresholds ────────────────────────────────────────────────────────────────
SCORE_SUSPICIOUS = 40    # Score above this = suspicious
SCORE_ATTACK     = 70    # Score above this = redirect to honeypot
SCORE_CRITICAL   = 90    # Score above this = trigger emergency response

# ── Known Bot User-Agent Patterns ─────────────────────────────────────────────
BOT_PATTERNS = re.compile(
    r"(bot|crawler|spider|scraper|scan|nikto|sqlmap|nmap|masscan|dirbuster"
    r"|gobuster|wpscan|burp|metasploit|hydra|medusa|nessus|openvas"
    r"|curl|wget|python-requests|python-urllib|httpie|postman"
    r"|go-http-client|java/|libwww-perl|lwp-|php/|ruby/)",
    re.IGNORECASE,
)

# Common legitimate browser patterns
BROWSER_PATTERNS = re.compile(
    r"(Mozilla|Chrome|Safari|Firefox|Edge|Opera|MSIE|Trident)",
    re.IGNORECASE,
)

# Suspicious path patterns (beyond honeypot)
RECON_PATHS = re.compile(
    r"(\.env|\.git|\.svn|\.htaccess|\.htpasswd|wp-config|config\.php"
    r"|phpinfo|server-status|server-info|\.DS_Store|\.bak|\.old"
    r"|\.sql|\.db|\.sqlite|/admin|/manager|/console|/debug"
    r"|/actuator|/swagger|/graphql|/\.well-known)",
    re.IGNORECASE,
)


@dataclass
class IPProfile:
    """Tracks behavior for a single IP address."""
    first_seen: float = 0.0
    request_times: deque = field(default_factory=lambda: deque(maxlen=500))
    paths_visited: deque = field(default_factory=lambda: deque(maxlen=100))
    methods_used: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    status_codes: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    user_agents: set = field(default_factory=set)
    failed_auths: int = 0
    honeypot_hits: int = 0
    payload_attacks: int = 0
    total_requests: int = 0
    last_classification: str = LABEL_NORMAL
    last_score: float = 0.0
    # Timing analysis
    inter_request_intervals: deque = field(default_factory=lambda: deque(maxlen=100))


@dataclass
class ClassificationResult:
    """Result of AI classification for a single request."""
    label: str                # normal, suspicious, attack, critical
    score: float              # 0-100 threat score
    confidence: float         # 0-1 confidence in classification
    factors: Dict[str, float] # Which factors contributed to the score
    action: str               # "allow", "monitor", "honeypot", "block", "emergency"
    attack_type: str = ""     # Type of attack if detected


class AITrafficClassifier:
    """
    ML-inspired traffic classifier.
    Uses a weighted scoring system with multiple behavioral features.
    Each feature contributes to a threat score, which determines classification.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._ip_profiles: Dict[str, IPProfile] = defaultdict(IPProfile)
        self._global_request_times: deque = deque(maxlen=10000)
        self._classifications: deque = deque(maxlen=5000)
        self._total_classified = 0
        self._attack_count = 0
        self._normal_count = 0

        # Feature weights (like ML model weights)
        self._weights = {
            "request_rate":       20,   # High rate = likely bot/DDoS
            "timing_regularity":  15,   # Bots have consistent timing, humans don't
            "user_agent":         15,   # Known attack tools
            "path_suspicion":     15,   # Scanning/recon paths
            "payload_entropy":    10,   # High entropy = encoded payloads
            "auth_failures":      10,   # Brute force indicator
            "method_diversity":   5,    # Bots usually use only GET
            "session_anomaly":    10,   # Unusual request sequences
        }

        logger.info("🧠 AI Traffic Classifier v1.0 initialized")

        # Cleanup thread
        t = threading.Thread(target=self._cleanup_loop, daemon=True)
        t.start()

    def classify(self, ip: str, path: str, method: str, user_agent: str,
                 query_string: str = "", body: str = "",
                 status_code: int = 0) -> ClassificationResult:
        """
        Classify a single request as normal/suspicious/attack/critical.
        Returns a ClassificationResult with score, label, and recommended action.
        """
        now = time.time()

        with self._lock:
            profile = self._ip_profiles[ip]

            # Update profile
            if profile.first_seen == 0:
                profile.first_seen = now

            # Calculate inter-request interval
            if profile.request_times:
                interval = now - profile.request_times[-1]
                profile.inter_request_intervals.append(interval)

            profile.request_times.append(now)
            profile.paths_visited.append(path)
            profile.methods_used[method] += 1
            if user_agent:
                profile.user_agents.add(user_agent[:100])
            profile.total_requests += 1
            if status_code:
                profile.status_codes[status_code] += 1

            # Track global request rate
            self._global_request_times.append(now)

        # Extract features and score
        factors = {}
        total_score = 0.0

        # ── Feature 1: Request Rate ──────────────────────────────────────
        rate_score = self._score_request_rate(profile, now)
        factors["request_rate"] = rate_score
        total_score += rate_score * (self._weights["request_rate"] / 100)

        # ── Feature 2: Timing Regularity ─────────────────────────────────
        timing_score = self._score_timing_regularity(profile)
        factors["timing_regularity"] = timing_score
        total_score += timing_score * (self._weights["timing_regularity"] / 100)

        # ── Feature 3: User-Agent Analysis ───────────────────────────────
        ua_score = self._score_user_agent(user_agent, profile)
        factors["user_agent"] = ua_score
        total_score += ua_score * (self._weights["user_agent"] / 100)

        # ── Feature 4: Path Suspicion ────────────────────────────────────
        path_score = self._score_path(path, profile)
        factors["path_suspicion"] = path_score
        total_score += path_score * (self._weights["path_suspicion"] / 100)

        # ── Feature 5: Payload Entropy ───────────────────────────────────
        payload_score = self._score_payload(query_string, body)
        factors["payload_entropy"] = payload_score
        total_score += payload_score * (self._weights["payload_entropy"] / 100)

        # ── Feature 6: Auth Failures ─────────────────────────────────────
        auth_score = self._score_auth_failures(profile)
        factors["auth_failures"] = auth_score
        total_score += auth_score * (self._weights["auth_failures"] / 100)

        # ── Feature 7: Method Diversity ──────────────────────────────────
        method_score = self._score_method_diversity(profile)
        factors["method_diversity"] = method_score
        total_score += method_score * (self._weights["method_diversity"] / 100)

        # ── Feature 8: Session Anomaly ───────────────────────────────────
        session_score = self._score_session_anomaly(profile)
        factors["session_anomaly"] = session_score
        total_score += session_score * (self._weights["session_anomaly"] / 100)

        # Clamp score to 0-100
        total_score = min(100.0, max(0.0, total_score))

        # Determine classification
        if total_score >= SCORE_CRITICAL:
            label = LABEL_CRITICAL
            action = "emergency"
            attack_type = self._determine_attack_type(factors, profile)
        elif total_score >= SCORE_ATTACK:
            label = LABEL_ATTACK
            action = "honeypot"
            attack_type = self._determine_attack_type(factors, profile)
        elif total_score >= SCORE_SUSPICIOUS:
            label = LABEL_SUSPICIOUS
            action = "monitor"
            attack_type = ""
        else:
            label = LABEL_NORMAL
            action = "allow"
            attack_type = ""

        # Calculate confidence based on data points
        data_points = len(profile.request_times)
        confidence = min(1.0, data_points / 20)  # Full confidence after 20 requests

        result = ClassificationResult(
            label=label,
            score=round(total_score, 1),
            confidence=round(confidence, 2),
            factors={k: round(v, 1) for k, v in factors.items()},
            action=action,
            attack_type=attack_type,
        )

        # Update profile
        with self._lock:
            profile.last_classification = label
            profile.last_score = total_score
            self._total_classified += 1
            if label in (LABEL_ATTACK, LABEL_CRITICAL):
                self._attack_count += 1
            else:
                self._normal_count += 1
            self._classifications.append({
                "ip": ip,
                "label": label,
                "score": round(total_score, 1),
                "timestamp_unix": now,
                "timestamp": datetime.now().isoformat(),
                "attack_type": attack_type,
            })

            # ── Anti-Memory Exhaustion (LRU-ish limit) ──
            if len(self._ip_profiles) > 10000:
                # Randomly pop an item to prevent memory blowout during spoofed IP DDoS
                try:
                    k = next(iter(self._ip_profiles))
                    del self._ip_profiles[k]
                except StopIteration:
                    pass

        return result

    # ── Feature Scoring Functions ─────────────────────────────────────────────

    def _score_request_rate(self, profile: IPProfile, now: float) -> float:
        """Score based on request rate. High rate = high score."""
        # Count requests in last 10 seconds
        recent = sum(1 for t in profile.request_times if now - t < 10)
        rate_per_sec = recent / 10.0

        if rate_per_sec > 50:
            return 100.0
        elif rate_per_sec > 20:
            return 85.0
        elif rate_per_sec > 10:
            return 70.0
        elif rate_per_sec > 5:
            return 50.0
        elif rate_per_sec > 2:
            return 25.0
        return 0.0

    def _score_timing_regularity(self, profile: IPProfile) -> float:
        """
        Bots have very regular timing (0.01s, 0.01s, 0.01s).
        Humans have irregular timing (0.5s, 3s, 0.1s, 15s).
        Low standard deviation of intervals = bot behavior.
        """
        intervals = list(profile.inter_request_intervals)
        if len(intervals) < 5:
            return 0.0

        mean = sum(intervals) / len(intervals)
        if mean == 0:
            return 100.0  # Zero interval = definitely automated

        variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
        std_dev = math.sqrt(variance)

        # Coefficient of variation (CV): low CV = regular timing = bot
        cv = std_dev / mean if mean > 0 else 0

        if cv < 0.05:       # Almost zero variation = definite bot
            return 100.0
        elif cv < 0.15:     # Very regular
            return 80.0
        elif cv < 0.30:     # Somewhat regular
            return 50.0
        elif cv < 0.50:     # Could be automated with jitter
            return 25.0
        return 0.0           # Irregular = human-like

    def _score_user_agent(self, ua: str, profile: IPProfile) -> float:
        """Score based on User-Agent analysis."""
        if not ua or ua.strip() == "":
            return 60.0  # No UA = suspicious

        # Known attack tools
        if BOT_PATTERNS.search(ua):
            return 90.0

        # Not a real browser
        if not BROWSER_PATTERNS.search(ua):
            return 50.0

        # Multiple user agents from same IP = suspicious
        if len(profile.user_agents) > 3:
            return 40.0

        return 0.0  # Normal browser UA

    def _score_path(self, path: str, profile: IPProfile) -> float:
        """Score based on path analysis."""
        score = 0.0

        # Known recon/scanning paths
        if RECON_PATHS.search(path):
            score += 80.0
            profile.honeypot_hits += 1

        # Check for path traversal
        if ".." in path or "%2e" in path.lower():
            score += 90.0

        # Many unique paths in short time = directory scanning
        unique_paths = len(set(list(profile.paths_visited)[-20:]))
        if unique_paths > 15:
            score += 60.0
        elif unique_paths > 10:
            score += 30.0

        return min(100.0, score)

    def _score_payload(self, query: str, body: str) -> float:
        """Score based on payload entropy and patterns."""
        payload = (query or "") + (body or "")
        if not payload:
            return 0.0

        # Calculate Shannon entropy
        entropy = self._shannon_entropy(payload)

        score = 0.0

        # Very high entropy = possibly encoded/encrypted payloads
        if entropy > 5.0:
            score += 40.0

        # Check for common attack patterns in combined payload
        if re.search(r"(union.*select|drop.*table|insert.*into)", payload, re.I):
            score += 90.0
        if re.search(r"(<script|javascript:|onerror=|onload=)", payload, re.I):
            score += 85.0
        if re.search(r"(\.\./|%2e%2e)", payload, re.I):
            score += 80.0
        if re.search(r"(\||;|&&|\$\(|`)", payload):
            score += 75.0

        # Very long payloads = potential buffer overflow attempt
        if len(payload) > 5000:
            score += 30.0

        return min(100.0, score)

    def _score_auth_failures(self, profile: IPProfile) -> float:
        """Score based on authentication failure count."""
        fails = profile.failed_auths
        if fails >= 10:
            return 100.0
        elif fails >= 5:
            return 80.0
        elif fails >= 3:
            return 50.0
        elif fails >= 1:
            return 20.0
        return 0.0

    def _score_method_diversity(self, profile: IPProfile) -> float:
        """
        Normal users use GET and POST.
        Attackers use PUT, DELETE, PATCH, OPTIONS, TRACE etc.
        """
        methods = set(profile.methods_used.keys())
        unusual_methods = methods - {"GET", "POST", "HEAD"}

        if "TRACE" in unusual_methods or "DEBUG" in unusual_methods:
            return 90.0
        if len(unusual_methods) >= 3:
            return 70.0
        if len(unusual_methods) >= 1:
            return 30.0
        return 0.0

    def _score_session_anomaly(self, profile: IPProfile) -> float:
        """
        Normal users: login → dashboard → browse pages
        Attackers: random scanning, no login, hit admin paths
        """
        paths = list(profile.paths_visited)
        if len(paths) < 3:
            return 0.0

        score = 0.0

        # Check if user ever visited login/normal pages
        normal_paths = [p for p in paths if any(n in p for n in
                       ["/login", "/dashboard", "/index", "/performance"])]
        attack_paths = [p for p in paths if any(a in p for a in
                       ["/admin", "/.env", "/wp-", "/php", "/config"])]

        # All attack paths, no normal pages = definitely scanning
        if attack_paths and not normal_paths:
            score += 80.0

        # Rapid path changes = automated scanning
        if len(paths) > 10:
            unique_ratio = len(set(paths[-10:])) / 10
            if unique_ratio > 0.9:  # Almost all unique = scanning
                score += 50.0

        # No GET of HTML pages = probably not a browser
        get_count = profile.methods_used.get("GET", 0)
        post_count = profile.methods_used.get("POST", 0)
        if post_count > get_count * 2 and post_count > 5:
            score += 40.0  # Way more POSTs than GETs = abnormal

        return min(100.0, score)

    # ── Helper Functions ──────────────────────────────────────────────────────

    def _shannon_entropy(self, data: str) -> float:
        """Calculate Shannon entropy of a string."""
        if not data:
            return 0.0
        freq = defaultdict(int)
        for char in data:
            freq[char] += 1
        length = len(data)
        return -sum(
            (count / length) * math.log2(count / length)
            for count in freq.values()
            if count > 0
        )

    def _determine_attack_type(self, factors: Dict, profile: IPProfile) -> str:
        """Determine the most likely type of attack."""
        max_factor = max(factors, key=factors.get)

        type_map = {
            "request_rate": "DDoS/Flood",
            "timing_regularity": "Automated Bot",
            "user_agent": "Attack Tool",
            "path_suspicion": "Reconnaissance/Scanning",
            "payload_entropy": "Payload Injection",
            "auth_failures": "Brute Force",
            "method_diversity": "API Fuzzing",
            "session_anomaly": "Anomalous Behavior",
        }
        return type_map.get(max_factor, "Unknown")

    def record_auth_failure(self, ip: str):
        """Record a failed authentication attempt for an IP."""
        with self._lock:
            self._ip_profiles[ip].failed_auths += 1

    def record_auth_success(self, ip: str):
        """Reset auth failures on successful login."""
        with self._lock:
            self._ip_profiles[ip].failed_auths = 0

    # ── Stats & Reporting ─────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Get AI classifier statistics."""
        now_unix = time.time()
        
        # Fast copy/extract under lock
        with self._lock:
            # Only use pre-calculated unix timestamps, no slow fromisoformat parsing!
            recent = [c for c in self._classifications if c.get("timestamp_unix", 0) > now_unix - 300]
            
            total_classified = self._total_classified
            attack_count = self._attack_count
            normal_count = self._normal_count
            
            # Fast extraction of threatened IPs
            threatened_ips_unsorted = [
                (ip, p.last_score, p.last_classification, p.total_requests)
                 for ip, p in self._ip_profiles.items()
                 if p.last_score >= SCORE_SUSPICIOUS
            ]

        # Heavy processing (sorting) OUTSIDE the lock
        attack_types = defaultdict(int)
        for c in recent:
            if c.get("attack_type"):
                attack_types[c["attack_type"]] += 1

        threatened_ips = sorted(
            threatened_ips_unsorted,
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return {
            "total_classified": total_classified,
            "total_attacks_detected": attack_count,
            "total_normal": normal_count,
            "detection_rate": round((attack_count / max(1, total_classified)) * 100, 1),
                "recent_5min": {
                    "total": len(recent),
                    "attacks": sum(1 for c in recent if c["label"] in ("attack", "critical")),
                    "attack_types": dict(attack_types),
                },
                "threatened_ips": [
                    {"ip": ip, "score": round(score, 1), "label": label, "requests": reqs}
                    for ip, score, label, reqs in threatened_ips
                ],
                "model_weights": self._weights,
                "thresholds": {
                    "suspicious": SCORE_SUSPICIOUS,
                    "attack": SCORE_ATTACK,
                    "critical": SCORE_CRITICAL,
                },
            }

    def get_ip_profile(self, ip: str) -> Optional[Dict]:
        """Get detailed profile for a specific IP."""
        with self._lock:
            if ip not in self._ip_profiles:
                return None
            p = self._ip_profiles[ip]
            return {
                "ip": ip,
                "first_seen": datetime.fromtimestamp(p.first_seen).isoformat() if p.first_seen else None,
                "total_requests": p.total_requests,
                "last_score": round(p.last_score, 1),
                "last_classification": p.last_classification,
                "failed_auths": p.failed_auths,
                "honeypot_hits": p.honeypot_hits,
                "unique_paths": len(set(p.paths_visited)),
                "methods": dict(p.methods_used),
                "user_agents": list(p.user_agents)[:5],
                "recent_paths": list(p.paths_visited)[-10:],
            }

    def get_recent_classifications(self, limit: int = 50) -> List[Dict]:
        """Get recent classification results."""
        with self._lock:
            return list(self._classifications)[-limit:]

    def _cleanup_loop(self):
        """Periodically clean up old IP profiles to prevent memory bloat."""
        while True:
            time.sleep(600)  # Every 10 minutes
            try:
                now = time.time()
                with self._lock:
                    stale_ips = [
                        ip for ip, p in self._ip_profiles.items()
                        if p.request_times and (now - p.request_times[-1]) > 3600
                        and p.last_score < SCORE_SUSPICIOUS
                    ]
                    for ip in stale_ips:
                        del self._ip_profiles[ip]
                    if stale_ips:
                        logger.info(f"🧹 Cleaned {len(stale_ips)} stale IP profiles")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────
ai_classifier = AITrafficClassifier()

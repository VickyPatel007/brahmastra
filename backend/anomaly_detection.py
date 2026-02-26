"""
Brahmastra ML Anomaly Detection Engine
=======================================
Uses statistical analysis (Z-score + moving averages) to detect 
unusual CPU, memory, and disk usage patterns.

No external ML libraries needed — pure Python with numpy-like math.
Learns normal patterns over time and flags deviations.
"""

import time
import logging
from collections import deque
from datetime import datetime
from typing import Optional

logger = logging.getLogger("Brahmastra-ML")


class AnomalyDetector:
    """
    Statistical anomaly detector using Z-score analysis.
    
    How it works:
    1. Collects metrics over time in a sliding window
    2. Calculates mean and standard deviation for each metric
    3. Flags values that deviate beyond a threshold (default: 2.5 std devs)
    4. Tracks anomaly streaks to reduce false positives
    """

    def __init__(self, window_size: int = 120, z_threshold: float = 2.5, min_samples: int = 20):
        """
        Args:
            window_size: Number of data points to keep (at 5s intervals, 120 = 10 min window)
            z_threshold: Z-score threshold to flag as anomaly (2.5 = 99.4% confidence)
            min_samples: Minimum samples needed before detection starts
        """
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.min_samples = min_samples

        # Sliding windows for each metric
        self.cpu_history = deque(maxlen=window_size)
        self.memory_history = deque(maxlen=window_size)
        self.disk_history = deque(maxlen=window_size)

        # Anomaly tracking
        self.anomalies = []
        self.max_anomalies = 200
        self.anomaly_streaks = {"cpu": 0, "memory": 0, "disk": 0}
        self.streak_threshold = 3  # Need 3 consecutive anomalous readings to trigger

        # Stats
        self.total_checks = 0
        self.total_anomalies_detected = 0
        self.started_at = datetime.now().isoformat()

        logger.info(f"🧠 ML Anomaly Detector initialized (window={window_size}, z={z_threshold})")

    def _calculate_stats(self, data: deque) -> tuple:
        """Calculate mean and standard deviation."""
        if len(data) < 2:
            return 0, 0
        n = len(data)
        mean = sum(data) / n
        variance = sum((x - mean) ** 2 for x in data) / (n - 1)
        std = variance ** 0.5
        return mean, std

    def _calculate_z_score(self, value: float, mean: float, std: float) -> float:
        """Calculate Z-score (how many std devs from mean)."""
        if std == 0:
            return 0
        return abs(value - mean) / std

    def _calculate_ema(self, data: deque, span: int = 12) -> float:
        """Exponential Moving Average — gives more weight to recent data."""
        if not data:
            return 0
        alpha = 2 / (span + 1)
        ema = data[0]
        for val in list(data)[1:]:
            ema = alpha * val + (1 - alpha) * ema
        return ema

    def analyze(self, cpu: float, memory: float, disk: float) -> dict:
        """
        Feed new metric values and check for anomalies.
        
        Returns:
            dict with anomaly analysis results
        """
        self.total_checks += 1
        timestamp = datetime.now().isoformat()

        # Add to history
        self.cpu_history.append(cpu)
        self.memory_history.append(memory)
        self.disk_history.append(disk)

        # Not enough data yet
        if len(self.cpu_history) < self.min_samples:
            return {
                "status": "learning",
                "samples": len(self.cpu_history),
                "needed": self.min_samples,
                "message": f"Learning baseline... ({len(self.cpu_history)}/{self.min_samples} samples)",
                "anomalies": [],
            }

        # Calculate stats for each metric
        cpu_mean, cpu_std = self._calculate_stats(self.cpu_history)
        mem_mean, mem_std = self._calculate_stats(self.memory_history)
        disk_mean, disk_std = self._calculate_stats(self.disk_history)

        # Calculate Z-scores
        cpu_z = self._calculate_z_score(cpu, cpu_mean, cpu_std)
        mem_z = self._calculate_z_score(memory, mem_mean, mem_std)
        disk_z = self._calculate_z_score(disk, disk_mean, disk_std)

        # EMA (trend detection)
        cpu_ema = self._calculate_ema(self.cpu_history)
        mem_ema = self._calculate_ema(self.memory_history)

        anomalies_found = []

        # Check CPU
        if cpu_z > self.z_threshold:
            self.anomaly_streaks["cpu"] += 1
            if self.anomaly_streaks["cpu"] >= self.streak_threshold:
                anomaly = {
                    "metric": "CPU",
                    "value": cpu,
                    "expected": cpu_mean,
                    "z_score": round(cpu_z, 2),
                    "deviation": round(cpu_z, 1),
                    "severity": "critical" if cpu > 90 else "high",
                    "timestamp": timestamp,
                }
                anomalies_found.append(anomaly)
        else:
            self.anomaly_streaks["cpu"] = 0

        # Check Memory
        if mem_z > self.z_threshold:
            self.anomaly_streaks["memory"] += 1
            if self.anomaly_streaks["memory"] >= self.streak_threshold:
                anomaly = {
                    "metric": "Memory",
                    "value": memory,
                    "expected": mem_mean,
                    "z_score": round(mem_z, 2),
                    "deviation": round(mem_z, 1),
                    "severity": "critical" if memory > 90 else "high",
                    "timestamp": timestamp,
                }
                anomalies_found.append(anomaly)
        else:
            self.anomaly_streaks["memory"] = 0

        # Check Disk (sudden changes only)
        if disk_z > self.z_threshold * 1.5:  # Higher threshold for disk
            self.anomaly_streaks["disk"] += 1
            if self.anomaly_streaks["disk"] >= self.streak_threshold:
                anomaly = {
                    "metric": "Disk",
                    "value": disk,
                    "expected": disk_mean,
                    "z_score": round(disk_z, 2),
                    "deviation": round(disk_z, 1),
                    "severity": "critical" if disk > 90 else "medium",
                    "timestamp": timestamp,
                }
                anomalies_found.append(anomaly)
        else:
            self.anomaly_streaks["disk"] = 0

        # Store anomalies
        for a in anomalies_found:
            self.anomalies.append(a)
            self.total_anomalies_detected += 1
        if len(self.anomalies) > self.max_anomalies:
            self.anomalies = self.anomalies[-self.max_anomalies:]

        return {
            "status": "monitoring",
            "anomalies": anomalies_found,
            "stats": {
                "cpu": {"current": round(cpu, 1), "mean": round(cpu_mean, 1), "std": round(cpu_std, 1), "z_score": round(cpu_z, 2), "ema": round(cpu_ema, 1)},
                "memory": {"current": round(memory, 1), "mean": round(mem_mean, 1), "std": round(mem_std, 1), "z_score": round(mem_z, 2), "ema": round(mem_ema, 1)},
                "disk": {"current": round(disk, 1), "mean": round(disk_mean, 1), "std": round(disk_std, 1), "z_score": round(disk_z, 2)},
            },
            "total_checks": self.total_checks,
            "total_anomalies": self.total_anomalies_detected,
            "samples": len(self.cpu_history),
        }

    def get_anomaly_history(self) -> list:
        """Get list of all detected anomalies (newest first)."""
        return list(reversed(self.anomalies))

    def get_status(self) -> dict:
        """Get current status of the anomaly detector."""
        return {
            "enabled": True,
            "started_at": self.started_at,
            "total_checks": self.total_checks,
            "total_anomalies": self.total_anomalies_detected,
            "window_size": self.window_size,
            "z_threshold": self.z_threshold,
            "samples_collected": len(self.cpu_history),
            "learning": len(self.cpu_history) < self.min_samples,
            "streaks": dict(self.anomaly_streaks),
        }


# ── Singleton ─────────────────────────────────────────────────
anomaly_detector = AnomalyDetector()

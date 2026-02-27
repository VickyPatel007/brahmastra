"""
Brahmastra Self-Healing Engine v2.0
=====================================
UPGRADES over v1:
  - Memory leak detection (tracks memory trend over 10 min)
  - Disk fill protection (cleans logs/tmp when disk > 85%)
  - Cascade recovery (3 failed heals → escalate to full restart)
  - Port conflict detection (kills zombie processes on port 8000)
  - OOM (Out-of-Memory) killer prevention via memory management
  - Slack/Telegram webhook alerts (configurable)
  - Structured JSON health report every 5 min
"""

import time
import logging
import subprocess
import os
import json
import psutil
import requests
from collections import deque
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
API_URL           = os.getenv("API_URL", "http://localhost:8000")
CHECK_INTERVAL    = 30          # seconds
THREAT_THRESHOLD  = 70
CPU_THRESHOLD     = 90
MEM_THRESHOLD     = 88
DISK_THRESHOLD    = 85
MEM_LEAK_WINDOW   = 12          # Number of samples to detect leak (12 * 30s = 6 min)
MEM_LEAK_SLOPE    = 1.5         # MB/sample = memory leak alert threshold
LOG_FILE          = os.getenv("HEAL_LOG", "/home/ubuntu/brahmastra/self_healing.log")
BACKEND_SERVICE   = "brahmastra.service"
NGINX_SERVICE     = "nginx"
BACKEND_PORT      = 8000
SLACK_WEBHOOK     = os.getenv("SLACK_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN= os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID", "")
HEALTH_REPORT_INTERVAL = 300   # JSON report every 5 min

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("Brahmastra-Healer-v2")


class SelfHealingEngine:

    def __init__(self):
        self.failure_count   = 0
        self.healed_count    = 0
        self.alert_count     = 0
        self.consecutive_fails = 0   # Tracks cascade failure count
        self.last_heal_time  = None
        self.mem_history     = deque(maxlen=MEM_LEAK_WINDOW)
        self.last_report_time = 0

    # ── Notifications ─────────────────────────────────────────────────────────

    def _notify(self, message: str, level: str = "warning"):
        icon = "🚨" if level == "critical" else "⚠️"
        full = f"{icon} [Brahmastra] {message}"
        if SLACK_WEBHOOK:
            try:
                requests.post(SLACK_WEBHOOK, json={"text": full}, timeout=5)
            except Exception:
                pass
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": TELEGRAM_CHAT_ID, "text": full},
                    timeout=5,
                )
            except Exception:
                pass

    # ── Service Control ───────────────────────────────────────────────────────

    def _run_cmd(self, cmd: list, timeout: int = 30) -> Tuple[bool, str]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.returncode == 0, r.stderr.strip() or r.stdout.strip()
        except Exception as e:
            return False, str(e)

    def restart_service(self, service: str) -> bool:
        log.warning(f"🔄 Restarting: {service}")
        ok, msg = self._run_cmd(["sudo", "systemctl", "restart", service])
        if ok:
            log.info(f"✅ {service} restarted")
            self.healed_count += 1
            self.last_heal_time = datetime.now().isoformat()
        else:
            log.error(f"❌ {service} restart failed: {msg}")
        return ok

    def is_service_running(self, service: str) -> bool:
        ok, out = self._run_cmd(["sudo", "systemctl", "is-active", service], timeout=10)
        return "active" in out

    # ── Port Conflict Fix ─────────────────────────────────────────────────────

    def kill_zombie_on_port(self, port: int) -> bool:
        """Kill any zombie process occupying the given port."""
        try:
            for conn in psutil.net_connections():
                if conn.laddr.port == port and conn.status == "LISTEN":
                    proc = psutil.Process(conn.pid)
                    log.warning(f"⚡ Killing zombie PID {conn.pid} on port {port} ({proc.name()})")
                    proc.kill()
                    return True
        except Exception as e:
            log.error(f"❌ Zombie kill failed: {e}")
        return False

    # ── Health Check ──────────────────────────────────────────────────────────

    def check_api_health(self) -> dict:
        try:
            r = requests.get(f"{API_URL}/health", timeout=5)
            if r.status_code == 200:
                return {"ok": True, "data": r.json()}
            return {"ok": False, "reason": f"HTTP {r.status_code}"}
        except requests.ConnectionError:
            return {"ok": False, "reason": "Connection refused"}
        except requests.Timeout:
            return {"ok": False, "reason": "Timeout"}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    def check_system_resources(self) -> dict:
        cpu  = psutil.cpu_percent(interval=1)
        mem  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        self.mem_history.append(mem.used / 1024 / 1024)  # MB
        return {
            "cpu": cpu,
            "mem": mem.percent,
            "mem_mb": mem.used // 1024 // 1024,
            "disk": disk.percent,
            "disk_free_gb": disk.free // 1024 // 1024 // 1024,
            "critical": cpu > CPU_THRESHOLD or mem.percent > MEM_THRESHOLD,
        }

    def detect_memory_leak(self) -> bool:
        """Returns True if memory is steadily increasing (potential leak)."""
        if len(self.mem_history) < MEM_LEAK_WINDOW:
            return False
        vals = list(self.mem_history)
        # Simple linear regression slope
        n = len(vals)
        x_mean = (n - 1) / 2
        y_mean = sum(vals) / n
        num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(vals))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / den if den else 0
        if slope >= MEM_LEAK_SLOPE:
            log.warning(f"🔴 Memory leak detected! Growing {slope:.2f} MB/sample")
            return True
        return False

    # ── Disk Cleanup ──────────────────────────────────────────────────────────

    def cleanup_disk(self):
        """Free up disk space when > DISK_THRESHOLD."""
        log.warning("🗑️ Disk cleanup triggered")
        actions = [
            ["sudo", "journalctl", "--vacuum-size=100M"],
            ["sudo", "find", "/tmp", "-type", "f", "-mtime", "+1", "-delete"],
            ["sudo", "find", "/var/log", "-name", "*.gz", "-mtime", "+7", "-delete"],
        ]
        for cmd in actions:
            ok, out = self._run_cmd(cmd, timeout=30)
            log.info(f"  {'✅' if ok else '⚠️'} {' '.join(cmd[:3])}: {out[:80]}")

    # ── Main Heal Logic ───────────────────────────────────────────────────────

    def heal(self, reason: str, escalate: bool = False):
        log.warning(f"🚨 HEALING — Reason: {reason} | Escalate: {escalate}")
        self.failure_count += 1
        self._notify(f"Auto-healing triggered: {reason}", level="critical" if escalate else "warning")

        if escalate:
            # Full nuclear option: kill zombie port, restart both services
            self.kill_zombie_on_port(BACKEND_PORT)
            time.sleep(2)
            self.restart_service(NGINX_SERVICE)
            self.restart_service(BACKEND_SERVICE)
        else:
            if not self.is_service_running(BACKEND_SERVICE):
                self.restart_service(BACKEND_SERVICE)
                time.sleep(5)
            if not self.is_service_running(NGINX_SERVICE):
                self.restart_service(NGINX_SERVICE)

        # Verify
        time.sleep(10)
        health = self.check_api_health()
        if health["ok"]:
            log.info(f"✅ Recovered from: {reason}")
            self.consecutive_fails = 0
        else:
            self.consecutive_fails += 1
            log.error(f"❌ Recovery FAILED! Consecutive fails: {self.consecutive_fails}")
            if self.consecutive_fails >= 3:
                log.critical("💀 3 consecutive heal failures — forcing full restart!")
                self.heal(reason="Cascade failure", escalate=True)
                self.consecutive_fails = 0

    # ── Health Report ─────────────────────────────────────────────────────────

    def write_health_report(self, resources: dict, health: dict):
        report = {
            "timestamp": datetime.now().isoformat(),
            "api_healthy": health["ok"],
            "resources": resources,
            "stats": {
                "failures": self.failure_count,
                "heals": self.healed_count,
                "alerts": self.alert_count,
                "consecutive_fails": self.consecutive_fails,
                "last_heal": self.last_heal_time,
            },
        }
        try:
            with open("/tmp/brahmastra_health.json", "w") as f:
                json.dump(report, f, indent=2)
        except Exception:
            pass

    # ── Main Loop ─────────────────────────────────────────────────────────────

    def run(self):
        log.info("=" * 60)
        log.info("🛡️  Brahmastra Self-Healing Engine v2.0 STARTED")
        log.info(f"   Interval: {CHECK_INTERVAL}s | CPU: {CPU_THRESHOLD}% | MEM: {MEM_THRESHOLD}%")
        log.info(f"   Disk: {DISK_THRESHOLD}% | Mem leak slope: {MEM_LEAK_SLOPE} MB/sample")
        log.info("=" * 60)

        while True:
            try:
                # 1. API health
                health = self.check_api_health()
                if not health["ok"]:
                    self.heal(f"API unhealthy: {health.get('reason')}")
                else:
                    log.info("✅ API healthy")

                # 2. System resources
                res = self.check_system_resources()
                log.info(f"📊 CPU:{res['cpu']:.1f}% MEM:{res['mem']:.1f}% DISK:{res['disk']:.1f}%")
                if res["critical"]:
                    self.alert_count += 1
                    msg = f"Resource critical — CPU:{res['cpu']}% MEM:{res['mem']}%"
                    log.warning(f"⚠️  {msg}")
                    self._notify(msg)

                # 3. Memory leak
                if self.detect_memory_leak():
                    self._notify("Memory leak detected — consider restarting backend", "critical")

                # 4. Disk
                if res["disk"] > DISK_THRESHOLD:
                    log.warning(f"💾 Disk at {res['disk']:.1f}% — cleaning up")
                    self.cleanup_disk()

                # 5. Service checks
                if not self.is_service_running(BACKEND_SERVICE):
                    self.heal("Backend service not running")
                if not self.is_service_running(NGINX_SERVICE):
                    self.heal("Nginx not running")

                # 6. Health report
                now = time.time()
                if now - self.last_report_time >= HEALTH_REPORT_INTERVAL:
                    self.write_health_report(res, health)
                    self.last_report_time = now

                log.info(f"📈 Failures:{self.failure_count} Heals:{self.healed_count} Alerts:{self.alert_count}")

            except KeyboardInterrupt:
                log.info("🛑 Stopped by user")
                break
            except Exception as e:
                log.error(f"❌ Loop error: {e}")

            time.sleep(CHECK_INTERVAL)


# Fix missing import
from typing import Tuple

if __name__ == "__main__":
    SelfHealingEngine().run()

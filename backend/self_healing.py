"""
Brahmastra Self-Healing Engine
================================
Monitors system health and auto-recovers from failures.
Run this in the background on your EC2 instance.

Usage:
    python3 self_healing.py
    
Or as a systemd service (recommended).
"""

import time
import logging
import subprocess
import requests
import psutil
from datetime import datetime

# ── Config ──────────────────────────────────────────────────
API_URL          = "http://localhost:8000"
CHECK_INTERVAL   = 30         # seconds between health checks
THREAT_THRESHOLD = 70          # auto-act above this score
CPU_THRESHOLD    = 90          # % CPU - trigger alert
MEM_THRESHOLD    = 90          # % Memory - trigger alert
LOG_FILE         = "/home/ubuntu/brahmastra/self_healing.log"
BACKEND_SERVICE  = "brahmastra.service"
NGINX_SERVICE    = "nginx"

# ── Logger ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("Brahmastra-Healer")

# ────────────────────────────────────────────────────────────
class SelfHealingEngine:

    def __init__(self):
        self.failure_count   = 0
        self.healed_count    = 0
        self.alert_count     = 0
        self.last_heal_time  = None

    # ── Service control ──────────────────────────────────────
    def restart_service(self, service: str) -> bool:
        """Restart a systemd service."""
        try:
            log.warning(f"🔄 Restarting service: {service}")
            result = subprocess.run(
                ["sudo", "systemctl", "restart", service],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                log.info(f"✅ Service {service} restarted successfully")
                self.healed_count += 1
                self.last_heal_time = datetime.now().isoformat()
                return True
            else:
                log.error(f"❌ Failed to restart {service}: {result.stderr}")
                return False
        except Exception as e:
            log.error(f"❌ Exception restarting {service}: {e}")
            return False

    def is_service_running(self, service: str) -> bool:
        """Check if a systemd service is active."""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "is-active", service],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip() == "active"
        except Exception:
            return False

    # ── API Health Check ─────────────────────────────────────
    def check_api_health(self) -> dict:
        """Ping the FastAPI backend health endpoint."""
        try:
            resp = requests.get(f"{API_URL}/health", timeout=5)
            if resp.status_code == 200:
                return {"ok": True, "data": resp.json()}
            return {"ok": False, "reason": f"HTTP {resp.status_code}"}
        except requests.ConnectionError:
            return {"ok": False, "reason": "Connection refused"}
        except requests.Timeout:
            return {"ok": False, "reason": "Timeout"}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    # ── Threat Score Check ───────────────────────────────────
    def check_threat_score(self) -> int:
        """Fetch current threat score from API."""
        try:
            resp = requests.get(f"{API_URL}/api/threat/score", timeout=5)
            if resp.status_code == 200:
                return resp.json().get("threat_score", 0)
        except Exception:
            pass
        return 0

    # ── System Resource Check ─────────────────────────────────
    def check_system_resources(self) -> dict:
        """Check CPU, Memory, Disk usage."""
        cpu  = psutil.cpu_percent(interval=1)
        mem  = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        return {
            "cpu": cpu,
            "mem": mem,
            "disk": disk,
            "critical": cpu > CPU_THRESHOLD or mem > MEM_THRESHOLD
        }

    # ── Main Healing Logic ───────────────────────────────────
    def heal(self, reason: str):
        """Execute healing actions."""
        log.warning(f"🚨 Healing triggered — Reason: {reason}")
        self.failure_count += 1

        # Action 1: Restart backend if not running
        if not self.is_service_running(BACKEND_SERVICE):
            log.warning(f"⚠️  Backend service down! Restarting...")
            self.restart_service(BACKEND_SERVICE)
            time.sleep(5)

        # Action 2: Restart nginx if not running
        if not self.is_service_running(NGINX_SERVICE):
            log.warning(f"⚠️  Nginx down! Restarting...")
            self.restart_service(NGINX_SERVICE)

        # Action 3: Verify recovery
        time.sleep(10)
        health = self.check_api_health()
        if health["ok"]:
            log.info(f"✅ System recovered successfully after: {reason}")
        else:
            log.error(f"❌ Recovery failed! Manual intervention may be needed.")

    # ── Main Loop ─────────────────────────────────────────────
    def run(self):
        log.info("=" * 55)
        log.info("🛡️  Brahmastra Self-Healing Engine STARTED")
        log.info(f"   Check interval : {CHECK_INTERVAL}s")
        log.info(f"   Threat threshold: {THREAT_THRESHOLD}")
        log.info(f"   CPU threshold   : {CPU_THRESHOLD}%")
        log.info(f"   Memory threshold: {MEM_THRESHOLD}%")
        log.info("=" * 55)

        while True:
            try:
                log.info("🔍 Running health check...")

                # 1. API health check
                health = self.check_api_health()
                if not health["ok"]:
                    self.heal(f"API unhealthy: {health.get('reason')}")
                else:
                    log.info(f"✅ API healthy")

                # 2. System resource check
                resources = self.check_system_resources()
                log.info(f"📊 CPU:{resources['cpu']:.1f}% | MEM:{resources['mem']:.1f}% | DISK:{resources['disk']:.1f}%")
                if resources["critical"]:
                    log.warning(f"⚠️  Resource threshold exceeded! CPU:{resources['cpu']}% MEM:{resources['mem']}%")
                    self.alert_count += 1

                # 3. Threat score check
                threat = self.check_threat_score()
                log.info(f"🔒 Threat score: {threat}")
                if threat > THREAT_THRESHOLD:
                    log.warning(f"🚨 HIGH THREAT DETECTED: {threat} > {THREAT_THRESHOLD}")
                    self.alert_count += 1
                    # In future: auto-block IPs, scale defenses, notify admin

                # 4. Service checks
                if not self.is_service_running(BACKEND_SERVICE):
                    self.heal("Backend service not running")
                if not self.is_service_running(NGINX_SERVICE):
                    self.heal("Nginx not running")

                # 5. Summary log
                log.info(
                    f"📈 Stats — Failures:{self.failure_count} | "
                    f"Healed:{self.healed_count} | Alerts:{self.alert_count}"
                )

            except KeyboardInterrupt:
                log.info("🛑 Self-Healing Engine stopped by user.")
                break
            except Exception as e:
                log.error(f"❌ Unexpected error in healing loop: {e}")

            time.sleep(CHECK_INTERVAL)


# ─── Entry point ────────────────────────────────────────────
if __name__ == "__main__":
    engine = SelfHealingEngine()
    engine.run()

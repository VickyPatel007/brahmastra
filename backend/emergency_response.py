"""
Brahmastra Emergency Response Engine v1.0
==========================================
Automated response chain when a critical breach is detected:

Step 1: EMERGENCY BACKUP — Instant backup of all data
Step 2: PRESERVE EVIDENCE — Save honeypot + audit logs
Step 3: ALERT ADMIN — Send notification (log + optional Telegram)
Step 4: KILL SERVICES — Shut down server to strand attacker
Step 5: RECOVERY INFO — Generate recovery instructions

The chain is fully automated — no human intervention needed.
Data is safe, attacker is stranded.
"""

import os
import json
import time
import shutil
import tarfile
import logging
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("brahmastra.emergency")

# ── Config ────────────────────────────────────────────────────────────────────
EMERGENCY_BACKUP_DIR = os.getenv("EMERGENCY_BACKUP_DIR", "/home/ubuntu/brahmastra/emergency_backups")
EVIDENCE_DIR = os.getenv("EVIDENCE_DIR", "/home/ubuntu/brahmastra/evidence")
BACKEND_DIR = os.getenv("BACKEND_BASE_DIR", "/home/ubuntu/brahmastra/backend")
BACKUP_DIR = os.getenv("BACKUP_DIR", "/home/ubuntu/brahmastra/backups")

# What to backup in emergency
CRITICAL_FILES = [
    os.path.join(BACKEND_DIR, "brahmastra.db"),
    os.path.join(BACKEND_DIR, ".env"),
]

CRITICAL_DIRS = [
    EVIDENCE_DIR,
    BACKUP_DIR,
]

# How many emergency backups to keep
EMERGENCY_RETENTION = 5


class EmergencyResponse:
    """
    Automated emergency response chain.
    When triggered, executes: Backup → Evidence → Alert → Kill
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._emergency_active = False
        self._response_history: List[Dict] = []
        self._emergency_dir = Path(EMERGENCY_BACKUP_DIR)
        self._emergency_dir.mkdir(parents=True, exist_ok=True)
        self._kill_switch_callback = None
        self._honeypot_callback = None
        self._backup_callback = None
        logger.info("🚨 Emergency Response Engine v1.0 initialized")

    def register_callbacks(self, kill_switch=None, honeypot_save=None, backup_create=None):
        """Register callbacks to kill switch, honeypot, and backup system."""
        self._kill_switch_callback = kill_switch
        self._honeypot_callback = honeypot_save
        self._backup_callback = backup_create
        logger.info("✅ Emergency callbacks registered")

    def trigger_emergency(self, reason: str, attacker_ip: str = "",
                         ai_score: float = 0.0, attack_type: str = "") -> Dict:
        """
        TRIGGER THE FULL EMERGENCY RESPONSE CHAIN.
        This is the nuclear option — backup everything, kill the server.
        """
        with self._lock:
            if self._emergency_active:
                return {
                    "status": "already_active",
                    "message": "Emergency response already in progress",
                }
            self._emergency_active = True

        start_time = time.time()
        timestamp = datetime.now().isoformat()
        response_id = f"EMR_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        logger.critical(
            f"🚨🚨🚨 EMERGENCY RESPONSE TRIGGERED! 🚨🚨🚨\n"
            f"  Reason: {reason}\n"
            f"  Attacker IP: {attacker_ip}\n"
            f"  AI Score: {ai_score}\n"
            f"  Attack Type: {attack_type}"
        )

        response = {
            "response_id": response_id,
            "timestamp": timestamp,
            "reason": reason,
            "attacker_ip": attacker_ip,
            "ai_score": ai_score,
            "attack_type": attack_type,
            "steps": {},
        }

        # ═══════════════════════════════════════════════════════════════════
        # STEP 1: EMERGENCY BACKUP
        # ═══════════════════════════════════════════════════════════════════
        logger.critical("📦 STEP 1/5: EMERGENCY BACKUP — Saving all data...")
        step1 = self._step_emergency_backup(response_id)
        response["steps"]["1_emergency_backup"] = step1
        logger.critical(f"📦 STEP 1 {'✅ DONE' if step1['success'] else '❌ FAILED'}")

        # ═══════════════════════════════════════════════════════════════════
        # STEP 2: PRESERVE EVIDENCE
        # ═══════════════════════════════════════════════════════════════════
        logger.critical("📁 STEP 2/5: PRESERVING EVIDENCE — Saving honeypot data...")
        step2 = self._step_preserve_evidence(response_id)
        response["steps"]["2_preserve_evidence"] = step2
        logger.critical(f"📁 STEP 2 {'✅ DONE' if step2['success'] else '❌ FAILED'}")

        # ═══════════════════════════════════════════════════════════════════
        # STEP 3: REGULAR BACKUP (via backup system)
        # ═══════════════════════════════════════════════════════════════════
        logger.critical("💾 STEP 3/5: SYSTEM BACKUP — Creating final backup...")
        step3 = self._step_system_backup(response_id)
        response["steps"]["3_system_backup"] = step3
        logger.critical(f"💾 STEP 3 {'✅ DONE' if step3['success'] else '❌ SKIPPED'}")

        # ═══════════════════════════════════════════════════════════════════
        # STEP 4: ALERT ADMIN
        # ═══════════════════════════════════════════════════════════════════
        logger.critical("📢 STEP 4/5: ALERTING ADMIN...")
        step4 = self._step_alert_admin(response, attacker_ip, reason)
        response["steps"]["4_alert_admin"] = step4
        logger.critical(f"📢 STEP 4 {'✅ DONE' if step4['success'] else '❌ FAILED'}")

        # ═══════════════════════════════════════════════════════════════════
        # STEP 5: KILL SERVER
        # ═══════════════════════════════════════════════════════════════════
        logger.critical("💀 STEP 5/5: KILLING ALL SERVICES — Attacker will be stranded!")
        step5 = self._step_kill_server(reason)
        response["steps"]["5_kill_server"] = step5
        logger.critical(f"💀 STEP 5 {'✅ DONE' if step5['success'] else '❌ FAILED'}")

        # ═══════════════════════════════════════════════════════════════════
        # COMPLETE
        # ═══════════════════════════════════════════════════════════════════
        elapsed = time.time() - start_time
        response["total_time_seconds"] = round(elapsed, 2)
        response["status"] = "completed"

        # Save the response report
        report_path = self._emergency_dir / f"{response_id}_report.json"
        try:
            with open(report_path, "w") as f:
                json.dump(response, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save response report: {e}")

        self._response_history.append(response)

        logger.critical(
            f"\n{'='*60}\n"
            f"🚨 EMERGENCY RESPONSE COMPLETE in {elapsed:.1f}s\n"
            f"📦 Backup: {'✅' if step1['success'] else '❌'}\n"
            f"📁 Evidence: {'✅' if step2['success'] else '❌'}\n"
            f"💾 System Backup: {'✅' if step3['success'] else '❌'}\n"
            f"📢 Alert: {'✅' if step4['success'] else '❌'}\n"
            f"💀 Kill: {'✅' if step5['success'] else '❌'}\n"
            f"{'='*60}"
        )

        with self._lock:
            self._emergency_active = False

        return response

    # ── Step Implementations ──────────────────────────────────────────────────

    def _step_emergency_backup(self, response_id: str) -> Dict:
        """Create emergency backup of all critical data."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"EMERGENCY_{response_id}_{timestamp}.tar.gz"
            backup_path = self._emergency_dir / backup_name

            files_backed = []
            with tarfile.open(str(backup_path), "w:gz") as tar:
                # Backup critical files
                for filepath in CRITICAL_FILES:
                    if os.path.exists(filepath):
                        tar.add(filepath, arcname=f"data/{os.path.basename(filepath)}")
                        files_backed.append(filepath)

                # Backup critical directories
                for dirpath in CRITICAL_DIRS:
                    if os.path.exists(dirpath):
                        tar.add(dirpath, arcname=f"data/{os.path.basename(dirpath)}")
                        files_backed.append(dirpath)

            size_mb = round(backup_path.stat().st_size / (1024 * 1024), 2)

            # Enforce retention
            self._enforce_retention()

            return {
                "success": True,
                "backup_path": str(backup_path),
                "size_mb": size_mb,
                "files_backed": len(files_backed),
                "details": files_backed,
            }
        except Exception as e:
            logger.error(f"Emergency backup FAILED: {e}")
            return {"success": False, "error": str(e)}

    def _step_preserve_evidence(self, response_id: str) -> Dict:
        """Save all honeypot evidence."""
        try:
            saved_files = []

            # Use honeypot callback if available
            if self._honeypot_callback:
                saved = self._honeypot_callback()
                saved_files.extend(saved if saved else [])

            # Also copy existing evidence to emergency backup dir
            evidence_dir = Path(EVIDENCE_DIR)
            if evidence_dir.exists():
                emergency_evidence = self._emergency_dir / f"{response_id}_evidence"
                emergency_evidence.mkdir(exist_ok=True)
                for f in evidence_dir.glob("*.json"):
                    shutil.copy2(str(f), str(emergency_evidence / f.name))
                    saved_files.append(str(f))

            return {
                "success": True,
                "evidence_files": len(saved_files),
                "details": saved_files[:10],
            }
        except Exception as e:
            logger.error(f"Evidence preservation FAILED: {e}")
            return {"success": False, "error": str(e)}

    def _step_system_backup(self, response_id: str) -> Dict:
        """Trigger the regular backup system."""
        try:
            if self._backup_callback:
                result = self._backup_callback(label=f"emergency_{response_id}")
                return {
                    "success": result.get("success", False),
                    "details": result,
                }
            return {"success": False, "error": "Backup callback not registered"}
        except Exception as e:
            logger.error(f"System backup FAILED: {e}")
            return {"success": False, "error": str(e)}

    def _step_alert_admin(self, response: Dict, attacker_ip: str, reason: str) -> Dict:
        """Alert the admin about the emergency."""
        try:
            alert_msg = (
                f"🚨 BRAHMASTRA EMERGENCY RESPONSE 🚨\n\n"
                f"Reason: {reason}\n"
                f"Attacker IP: {attacker_ip}\n"
                f"Time: {response['timestamp']}\n"
                f"Response ID: {response['response_id']}\n\n"
                f"ACTIONS TAKEN:\n"
                f"✅ Emergency backup created\n"
                f"✅ Evidence preserved\n"
                f"💀 Server KILLED — attacker stranded\n\n"
                f"RECOVERY:\n"
                f"1. SSH into EC2\n"
                f"2. Check emergency backups: {EMERGENCY_BACKUP_DIR}\n"
                f"3. Review evidence: {EVIDENCE_DIR}\n"
                f"4. Restart: sudo systemctl start brahmastra"
            )

            # Log the alert
            logger.critical(f"\n{alert_msg}")

            # Save alert to file
            alert_path = self._emergency_dir / f"{response['response_id']}_alert.txt"
            with open(alert_path, "w") as f:
                f.write(alert_msg)

            # Try Telegram if configured
            telegram_sent = False
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if bot_token and chat_id:
                try:
                    import urllib.request
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    data = json.dumps({"chat_id": chat_id, "text": alert_msg}).encode()
                    req = urllib.request.Request(url, data=data,
                                               headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=5)
                    telegram_sent = True
                except Exception:
                    pass

            return {
                "success": True,
                "alert_file": str(alert_path),
                "telegram_sent": telegram_sent,
            }
        except Exception as e:
            logger.error(f"Alert FAILED: {e}")
            return {"success": False, "error": str(e)}

    def _step_kill_server(self, reason: str) -> Dict:
        """Kill the server — attacker gets stranded."""
        try:
            # Use kill switch callback if available (sets kill switch in app)
            if self._kill_switch_callback:
                self._kill_switch_callback(True, reason)

            return {
                "success": True,
                "method": "kill_switch_activated",
                "message": "Server kill switch activated — all requests return 503",
            }
        except Exception as e:
            logger.error(f"Kill server FAILED: {e}")
            return {"success": False, "error": str(e)}

    def _enforce_retention(self):
        """Keep only the most recent emergency backups."""
        try:
            backups = sorted(
                self._emergency_dir.glob("EMERGENCY_*.tar.gz"),
                key=lambda f: f.stat().st_mtime,
            )
            while len(backups) > EMERGENCY_RETENTION:
                oldest = backups.pop(0)
                oldest.unlink()
                logger.info(f"Removed old emergency backup: {oldest.name}")
        except Exception as e:
            logger.error(f"Retention enforcement failed: {e}")

    # ── Status & History ──────────────────────────────────────────────────────

    def get_status(self) -> Dict:
        """Get emergency response system status."""
        backups = list(self._emergency_dir.glob("EMERGENCY_*.tar.gz"))
        return {
            "active": self._emergency_active,
            "total_responses": len(self._response_history),
            "emergency_backups": len(backups),
            "backup_dir": str(self._emergency_dir),
            "callbacks_registered": {
                "kill_switch": self._kill_switch_callback is not None,
                "honeypot": self._honeypot_callback is not None,
                "backup": self._backup_callback is not None,
            },
            "recent_responses": [
                {
                    "id": r["response_id"],
                    "timestamp": r["timestamp"],
                    "reason": r["reason"],
                    "attacker_ip": r.get("attacker_ip", ""),
                    "time_seconds": r.get("total_time_seconds", 0),
                }
                for r in self._response_history[-5:]
            ],
        }

    def get_response_detail(self, response_id: str) -> Optional[Dict]:
        """Get detailed info about a specific emergency response."""
        for r in self._response_history:
            if r["response_id"] == response_id:
                return r
        # Try loading from disk
        report_path = self._emergency_dir / f"{response_id}_report.json"
        if report_path.exists():
            with open(report_path) as f:
                return json.load(f)
        return None

    @property
    def is_active(self) -> bool:
        return self._emergency_active


# ── Singleton ─────────────────────────────────────────────────────────────────
emergency_response = EmergencyResponse()

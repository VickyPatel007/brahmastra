"""
Brahmastra Alert System — Slack + Telegram Webhooks
====================================================
Sends real-time security alerts to Slack and Telegram channels.

Setup:
  1. Slack: Create an Incoming Webhook at https://api.slack.com/messaging/webhooks
  2. Telegram: Create a bot via @BotFather, get the chat_id from @userinfobot

Then set env vars:
  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz
  TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
  TELEGRAM_CHAT_ID=your_chat_id
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger("Brahmastra-Alerts")

# ── Config from env ────────────────────────────────────────────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

ALERT_ICONS = {
    "critical": "🚨",
    "high": "⚠️",
    "medium": "🔶",
    "low": "ℹ️",
    "info": "📌",
}


class AlertService:
    """Sends alerts to Slack and Telegram."""

    def __init__(self):
        self.slack_enabled = bool(SLACK_WEBHOOK_URL)
        self.telegram_enabled = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
        self.alert_history = []
        self.max_history = 100

        if self.slack_enabled:
            logger.info("✅ Slack alerts enabled")
        if self.telegram_enabled:
            logger.info("✅ Telegram alerts enabled")
        if not self.slack_enabled and not self.telegram_enabled:
            logger.warning("⚠️ No alert channels configured (set SLACK_WEBHOOK_URL or TELEGRAM_BOT_TOKEN)")

    # ── Send to Slack ─────────────────────────────────────────
    async def send_slack(self, title: str, message: str, severity: str = "info", fields: dict = None):
        if not self.slack_enabled:
            return False

        color_map = {"critical": "#ef4444", "high": "#f59e0b", "medium": "#667eea", "low": "#10b981", "info": "#6b7280"}
        icon = ALERT_ICONS.get(severity, "📌")

        payload = {
            "attachments": [{
                "color": color_map.get(severity, "#6b7280"),
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"{icon} {title}", "emoji": True}
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": message}
                    },
                    {
                        "type": "context",
                        "elements": [
                            {"type": "mrkdwn", "text": f"*Severity:* {severity.upper()} | *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                        ]
                    }
                ]
            }]
        }

        # Add extra fields if provided
        if fields:
            field_blocks = [{"type": "mrkdwn", "text": f"*{k}:* {v}"} for k, v in fields.items()]
            payload["attachments"][0]["blocks"].insert(2, {
                "type": "section",
                "fields": field_blocks
            })

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
                if resp.status_code == 200:
                    logger.info(f"✅ Slack alert sent: {title}")
                    return True
                else:
                    logger.error(f"❌ Slack error {resp.status_code}: {resp.text}")
                    return False
        except Exception as e:
            logger.error(f"❌ Slack send failed: {e}")
            return False

    # ── Send to Telegram ──────────────────────────────────────
    async def send_telegram(self, title: str, message: str, severity: str = "info"):
        if not self.telegram_enabled:
            return False

        icon = ALERT_ICONS.get(severity, "📌")
        text = (
            f"{icon} *{title}*\n\n"
            f"{message}\n\n"
            f"🔹 *Severity:* `{severity.upper()}`\n"
            f"🕐 *Time:* `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    logger.info(f"✅ Telegram alert sent: {title}")
                    return True
                else:
                    logger.error(f"❌ Telegram error {resp.status_code}: {resp.text}")
                    return False
        except Exception as e:
            logger.error(f"❌ Telegram send failed: {e}")
            return False

    # ── Send to ALL configured channels ───────────────────────
    async def send_alert(self, title: str, message: str, severity: str = "info", fields: dict = None):
        """Send alert to all configured channels (Slack + Telegram)."""
        self.alert_history.append({
            "title": title,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self.alert_history) > self.max_history:
            self.alert_history = self.alert_history[-self.max_history:]

        results = await asyncio.gather(
            self.send_slack(title, message, severity, fields),
            self.send_telegram(title, message, severity),
            return_exceptions=True,
        )

        success = any(r is True for r in results)
        if not success:
            logger.info(f"📝 Alert logged (no channels configured): {title} — {message}")
        return success

    # ── Pre-built alert types ─────────────────────────────────
    async def alert_ip_banned(self, ip: str, reason: str = "Repeated failed logins"):
        await self.send_alert(
            title="IP Address Banned",
            message=f"IP `{ip}` has been automatically banned.\n*Reason:* {reason}",
            severity="high",
            fields={"IP": ip, "Action": "Auto-banned"},
        )

    async def alert_honeypot_hit(self, ip: str, path: str):
        await self.send_alert(
            title="Honeypot Triggered",
            message=f"IP `{ip}` accessed honeypot endpoint `{path}`.\nThis IP has been flagged as suspicious.",
            severity="medium",
            fields={"IP": ip, "Path": path},
        )

    async def alert_kill_switch(self, triggered_by: str):
        await self.send_alert(
            title="KILL SWITCH ACTIVATED",
            message=f"Kill switch was triggered by `{triggered_by}`.\nAll defensive measures are now active.",
            severity="critical",
        )

    async def alert_high_threat(self, score: int, level: str):
        await self.send_alert(
            title="High Threat Score Detected",
            message=f"Threat score has reached *{score}* (level: `{level}`).\nMonitor the dashboard immediately.",
            severity="high",
            fields={"Score": str(score), "Level": level},
        )

    async def alert_anomaly(self, metric: str, value: float, expected: float, deviation: float):
        await self.send_alert(
            title=f"Anomaly Detected: {metric}",
            message=(
                f"*{metric}* is at `{value:.1f}%` — expected ~`{expected:.1f}%`.\n"
                f"Deviation: `{deviation:.1f}x` standard deviations from normal."
            ),
            severity="high",
            fields={"Metric": metric, "Current": f"{value:.1f}%", "Expected": f"{expected:.1f}%"},
        )

    async def alert_system_recovery(self, service: str):
        await self.send_alert(
            title="Service Auto-Recovered",
            message=f"Service `{service}` was down and has been automatically restarted by the self-healing engine.",
            severity="medium",
        )

    def get_alert_history(self):
        return list(reversed(self.alert_history))


# ── Singleton ─────────────────────────────────────────────────
alert_service = AlertService()

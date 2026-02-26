"""
Brahmastra Email Service
========================
Sends transactional emails via AWS SES.
Falls back to console logging if SES is not configured.

Setup:
    1. Set SES_FROM_EMAIL env var (must be verified in SES)
    2. Set AWS_REGION env var (default: ap-south-1)
    3. Make sure EC2 instance role has ses:SendEmail permission
       OR set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY

Usage:
    from backend.email_service import email_service
    await email_service.send_verification_email(to_email, verify_link)
    await email_service.send_password_reset_email(to_email, reset_link)
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("brahmastra.email")

# ── Config ────────────────────────────────────────────────────────────────────
SES_FROM_EMAIL = os.getenv("SES_FROM_EMAIL", "")   # Must be SES-verified
AWS_REGION     = os.getenv("AWS_REGION", "ap-south-1")
SES_ENABLED    = bool(SES_FROM_EMAIL)


class EmailService:
    """
    Email service that uses AWS SES when configured,
    otherwise falls back to console logging.
    """

    def __init__(self):
        self._client = None
        if SES_ENABLED:
            try:
                import boto3
                self._client = boto3.client("ses", region_name=AWS_REGION)
                logger.info(f"✅ SES email service initialized (from: {SES_FROM_EMAIL})")
            except ImportError:
                logger.warning("⚠️ boto3 not installed — SES disabled. pip install boto3")
            except Exception as e:
                logger.error(f"❌ SES init failed: {e}")
        else:
            logger.warning(
                "⚠️ SES_FROM_EMAIL not set — emails will only be logged to console. "
                "Set SES_FROM_EMAIL env var to enable real email sending."
            )

    def _console_fallback(self, to_email: str, subject: str, body: str):
        """Log email to console when SES is not available."""
        separator = "=" * 60
        logger.info(f"\n{separator}")
        logger.info(f"📧 [MOCK EMAIL]")
        logger.info(f"   To     : {to_email}")
        logger.info(f"   Subject: {subject}")
        logger.info(f"   Body   :\n{body}")
        logger.info(f"{separator}")
        print(f"\n{separator}\n📧 TO: {to_email}\n📌 {subject}\n{body}\n{separator}\n")

    async def _send_ses(self, to_email: str, subject: str, html_body: str, text_body: str) -> bool:
        """Send email via AWS SES."""
        if not self._client:
            return False
        try:
            self._client.send_email(
                Source=SES_FROM_EMAIL,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                    },
                },
            )
            logger.info(f"✅ Email sent via SES to {to_email}: {subject}")
            return True
        except Exception as e:
            logger.error(f"❌ SES send failed to {to_email}: {e}")
            return False

    async def send_verification_email(self, to_email: str, verify_link: str) -> bool:
        """Send email verification link."""
        subject = "Verify Your Brahmastra Account"
        text_body = f"Click this link to verify your email:\n\n{verify_link}\n\nLink expires in 24 hours."
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0f0c29; color: #fff; padding: 40px; border-radius: 12px;">
            <h1 style="background: linear-gradient(135deg, #667eea, #764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2rem;">⚡ BRAHMASTRA</h1>
            <h2 style="color: #fff; margin-top: 20px;">Verify Your Email</h2>
            <p style="color: rgba(255,255,255,0.7); line-height: 1.6;">Click the button below to verify your email address and activate your account.</p>
            <a href="{verify_link}"
               style="display: inline-block; margin: 25px 0; padding: 14px 32px; background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 1rem;">
               ✅ Verify Email
            </a>
            <p style="color: rgba(255,255,255,0.4); font-size: 0.85rem;">Link expires in 24 hours. If you didn't create this account, ignore this email.</p>
        </div>
        """
        if self._client:
            return await self._send_ses(to_email, subject, html_body, text_body)
        self._console_fallback(to_email, subject, f"Verify link: {verify_link}")
        return True

    async def send_password_reset_email(self, to_email: str, reset_link: str) -> bool:
        """Send password reset link."""
        subject = "Reset Your Brahmastra Password"
        text_body = f"Click this link to reset your password:\n\n{reset_link}\n\nLink expires in 30 minutes."
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0f0c29; color: #fff; padding: 40px; border-radius: 12px;">
            <h1 style="background: linear-gradient(135deg, #667eea, #764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2rem;">⚡ BRAHMASTRA</h1>
            <h2 style="color: #fff; margin-top: 20px;">Reset Your Password</h2>
            <p style="color: rgba(255,255,255,0.7); line-height: 1.6;">We received a request to reset your password. Click the button below to set a new one.</p>
            <a href="{reset_link}"
               style="display: inline-block; margin: 25px 0; padding: 14px 32px; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 1rem;">
               🔓 Reset Password
            </a>
            <p style="color: rgba(255,255,255,0.4); font-size: 0.85rem;">Link expires in 30 minutes. If you didn't request a reset, ignore this email — your password remains unchanged.</p>
        </div>
        """
        if self._client:
            return await self._send_ses(to_email, subject, html_body, text_body)
        self._console_fallback(to_email, subject, f"Reset link: {reset_link}")
        return True

    async def send_security_alert(self, to_email: str, alert_message: str, ip: str) -> bool:
        """Send a security alert email."""
        subject = "🚨 Brahmastra Security Alert"
        text_body = f"Security Alert:\n{alert_message}\nSource IP: {ip}"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0f0c29; color: #fff; padding: 40px; border-radius: 12px; border: 1px solid rgba(239, 68, 68, 0.4);">
            <h1 style="color: #ef4444; font-size: 2rem;">🚨 Security Alert</h1>
            <h2 style="color: #fff; margin-top: 10px;">Brahmastra Detected a Threat</h2>
            <div style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p style="color: rgba(255,255,255,0.9);">{alert_message}</p>
                <p style="color: rgba(255,255,255,0.5); margin-top: 10px; font-size: 0.9rem;">Source IP: <code style="color: #ef4444;">{ip}</code></p>
            </div>
            <p style="color: rgba(255,255,255,0.4); font-size: 0.85rem;">This is an automated alert from your Brahmastra monitoring system.</p>
        </div>
        """
        if self._client:
            return await self._send_ses(to_email, subject, html_body, text_body)
        self._console_fallback(to_email, subject, f"{alert_message} | IP: {ip}")
        return True


# Singleton instance
email_service = EmailService()

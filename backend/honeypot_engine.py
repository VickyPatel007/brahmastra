"""
Brahmastra Honeypot Engine v1.0
================================
Interactive honeypot that traps attackers in a convincing fake environment.
Records ALL attacker activity for forensic evidence collection.

Features:
  - Convincing fake responses (WordPress admin, .env, phpMyAdmin, etc.)
  - Session tracking per attacker IP
  - Full evidence collection: headers, body, timing, paths
  - Forensic report generation (JSON) for police/legal team
  - Attacker profiling: attack type, tools used, techniques
"""

import json
import time
import os
import logging
import hashlib
import threading
from datetime import datetime
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger("brahmastra.honeypot")

# ── Config ────────────────────────────────────────────────────────────────────
EVIDENCE_DIR = os.getenv("EVIDENCE_DIR", "/home/ubuntu/brahmastra/evidence")
MAX_SESSIONS = 500      # Max concurrent attacker sessions
SESSION_TIMEOUT = 3600  # Session expires after 1 hour of inactivity


@dataclass
class AttackerAction:
    """A single action taken by an attacker in the honeypot."""
    timestamp: str
    method: str
    path: str
    headers: Dict[str, str]
    body: str
    query_string: str
    response_code: int
    response_type: str    # What fake response was served
    ip: str
    user_agent: str


@dataclass
class AttackerSession:
    """Full session for a single attacker."""
    session_id: str
    ip: str
    first_seen: str
    last_seen: str
    actions: List[AttackerAction] = field(default_factory=list)
    attack_types: set = field(default_factory=set)
    tools_detected: set = field(default_factory=set)
    paths_attempted: List[str] = field(default_factory=list)
    total_requests: int = 0
    payloads_captured: List[str] = field(default_factory=list)
    severity: str = "low"   # low, medium, high, critical
    evidence_saved: bool = False


class HoneypotEngine:
    """
    Interactive honeypot that serves convincing fake responses
    and collects forensic evidence.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: Dict[str, AttackerSession] = {}
        self._total_trapped = 0
        self._total_evidence_collected = 0

        # Ensure evidence directory exists
        self._evidence_dir = Path(EVIDENCE_DIR)
        self._evidence_dir.mkdir(parents=True, exist_ok=True)

        logger.info("🍯 Honeypot Engine v1.0 initialized")

        # Cleanup thread
        t = threading.Thread(target=self._cleanup_loop, daemon=True)
        t.start()

    def trap_request(self, ip: str, method: str, path: str,
                     headers: Dict, body: str = "",
                     query_string: str = "",
                     ai_score: float = 0.0,
                     attack_type: str = "") -> Dict:
        """
        Process an attacker's request through the honeypot.
        Returns a convincing fake response.
        """
        now = datetime.now()
        user_agent = headers.get("user-agent", "")

        with self._lock:
            # Get or create session
            session = self._get_or_create_session(ip, now)

            # Record the action
            action = AttackerAction(
                timestamp=now.isoformat(),
                method=method,
                path=path,
                headers={k: v for k, v in list(headers.items())[:20]},
                body=body[:5000] if body else "",
                query_string=query_string[:2000] if query_string else "",
                response_code=200,
                response_type="",
                ip=ip,
                user_agent=user_agent,
            )

            # Detect tools used
            self._detect_tools(user_agent, session)

            # Track attack type
            if attack_type:
                session.attack_types.add(attack_type)

            session.paths_attempted.append(path)
            session.total_requests += 1
            session.last_seen = now.isoformat()

            # Capture interesting payloads
            if body and len(body) > 0:
                session.payloads_captured.append(body[:2000])

            # Update severity
            session.severity = self._assess_severity(session, ai_score)

        # Generate fake response based on path
        response = self._generate_fake_response(path, method, body)
        action.response_type = response["type"]
        action.response_code = response["status_code"]

        with self._lock:
            session.actions.append(action)

            # Auto-save evidence if session gets large enough
            if len(session.actions) >= 20 and not session.evidence_saved:
                self._save_evidence(session)

        logger.warning(
            f"🍯 TRAPPED: {ip} → {method} {path} "
            f"[Session: {session.total_requests} reqs, Severity: {session.severity}]"
        )

        return response

    def _generate_fake_response(self, path: str, method: str, body: str = "") -> Dict:
        """Generate convincing fake responses based on the attacker's request."""
        path_lower = path.lower()

        # ── Fake .env file ────────────────────────────────────────────────
        if ".env" in path_lower:
            return {
                "type": "fake_env",
                "status_code": 200,
                "content_type": "text/plain",
                "body": self._fake_env_file(),
            }

        # ── Fake WordPress Admin ──────────────────────────────────────────
        if "wp-admin" in path_lower or "wp-login" in path_lower:
            return {
                "type": "fake_wordpress",
                "status_code": 200,
                "content_type": "text/html",
                "body": self._fake_wordpress_login(),
            }

        # ── Fake phpMyAdmin ───────────────────────────────────────────────
        if "phpmyadmin" in path_lower or "pma" in path_lower:
            return {
                "type": "fake_phpmyadmin",
                "status_code": 200,
                "content_type": "text/html",
                "body": self._fake_phpmyadmin(),
            }

        # ── Fake Database Dump ────────────────────────────────────────────
        if any(x in path_lower for x in [".sql", ".db", "backup", "dump"]):
            return {
                "type": "fake_database",
                "status_code": 200,
                "content_type": "application/octet-stream",
                "body": self._fake_db_dump(),
            }

        # ── Fake Config Files ─────────────────────────────────────────────
        if any(x in path_lower for x in ["config", ".yml", ".yaml", ".json", ".xml"]):
            return {
                "type": "fake_config",
                "status_code": 200,
                "content_type": "application/json",
                "body": self._fake_config(),
            }

        # ── Fake Admin Panel ──────────────────────────────────────────────
        if "admin" in path_lower or "manager" in path_lower or "console" in path_lower:
            return {
                "type": "fake_admin",
                "status_code": 200,
                "content_type": "text/html",
                "body": self._fake_admin_panel(),
            }

        # ── Fake API with User Data ───────────────────────────────────────
        if "users" in path_lower or "accounts" in path_lower:
            return {
                "type": "fake_user_api",
                "status_code": 200,
                "content_type": "application/json",
                "body": self._fake_user_data(),
            }

        # ── Default: Fake Server Error (makes attacker think they're close) ──
        return {
            "type": "fake_error",
            "status_code": 500,
            "content_type": "text/html",
            "body": self._fake_server_error(),
        }

    # ── Fake Response Generators ──────────────────────────────────────────────

    def _fake_env_file(self) -> str:
        return """# Server Configuration
APP_ENV=production
APP_DEBUG=false
APP_KEY=base64:fK3Yz0pX7mN9qR2sT5uW8xA1bC4dE6gH0
DB_CONNECTION=mysql
DB_HOST=rds-prod-db.c7abc123.us-east-1.rds.amazonaws.com
DB_PORT=3306
DB_DATABASE=brahmastra_prod
DB_USERNAME=admin_readonly
DB_PASSWORD=Pr0d_S3cur3_2024!xK9m
REDIS_HOST=redis-prod.abc123.cache.amazonaws.com
REDIS_PASSWORD=r3d1s_Cl0ud_P@ss!
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7HONEYPOT
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYHONEYPOT
AWS_DEFAULT_REGION=us-east-1
AWS_BUCKET=brahmastra-data-prod
MAIL_MAILER=ses
MAIL_HOST=email-smtp.us-east-1.amazonaws.com
STRIPE_SECRET=sk_live_51Abc123HONEYPOTKEYFAKE
JWT_SECRET=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.HONEYPOT
"""

    def _fake_wordpress_login(self) -> str:
        return """<!DOCTYPE html>
<html lang="en-US">
<head><title>Log In &lsaquo; Corporate Portal &mdash; WordPress</title>
<link rel="stylesheet" href="https://s.w.org/wp-includes/css/dashicons.min.css">
<style>body{background:#f1f1f1;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Oxygen-Sans,Ubuntu,Cantarell,"Helvetica Neue",sans-serif}
.login{width:320px;margin:0 auto;padding:8% 0 0}.login h1 a{background-image:url(https://s.w.org/images/wmark.png);width:84px;height:84px;display:block;margin:0 auto 25px}
.login form{margin-top:20px;margin-left:0;padding:26px 24px 46px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.13);border-radius:4px}
.login label{font-size:14px;color:#72777c}.login input[type=text],.login input[type=password]{width:100%;padding:3px;font-size:24px;margin:2px 6px 16px 0;border:1px solid #ddd}
.login .button-primary{float:right;background:#2271b1;border-color:#2271b1;color:#fff;padding:0 12px;font-size:13px;height:30px;cursor:pointer;border-radius:3px}</style></head>
<body class="login"><div class="login"><h1><a href="https://wordpress.org/">WordPress</a></h1>
<form method="post" action="/wp-login.php">
<p><label for="user_login">Username or Email Address</label><input type="text" name="log" id="user_login" size="20"></p>
<p><label for="user_pass">Password</label><input type="password" name="pwd" id="user_pass" size="25"></p>
<p class="forgetmenot"><label><input name="rememberme" type="checkbox" value="forever"> Remember Me</label></p>
<p class="submit"><input type="submit" name="wp-submit" class="button button-primary" value="Log In"></p></form>
<p><a href="/wp-login.php?action=lostpassword">Lost your password?</a></p></div></body></html>"""

    def _fake_phpmyadmin(self) -> str:
        return """<!DOCTYPE html>
<html><head><title>phpMyAdmin 5.2.1</title>
<style>body{margin:0;font-family:sans-serif;background:#f5f5f5}
.header{background:#2962ff;color:#fff;padding:10px 20px;display:flex;align-items:center}
.header h1{margin:0;font-size:18px}.sidebar{width:250px;background:#fff;float:left;height:calc(100vh - 50px);border-right:1px solid #ddd;padding:10px}
.sidebar a{display:block;padding:5px 10px;color:#333;text-decoration:none;font-size:13px}.sidebar a:hover{background:#e3f2fd}
.main{margin-left:270px;padding:20px}</style></head>
<body><div class="header"><h1>phpMyAdmin</h1></div>
<div class="sidebar"><strong>Server: rds-prod-db</strong><br><br>
<a href="#">📁 brahmastra_prod</a>
<a href="#" style="padding-left:25px">📄 users (2,847 rows)</a>
<a href="#" style="padding-left:25px">📄 payments (12,394 rows)</a>
<a href="#" style="padding-left:25px">📄 api_keys (156 rows)</a>
<a href="#" style="padding-left:25px">📄 sessions (543 rows)</a>
<a href="#" style="padding-left:25px">📄 audit_log (89,234 rows)</a>
<a href="#">📁 information_schema</a>
<a href="#">📁 mysql</a></div>
<div class="main"><h2>Welcome to phpMyAdmin 5.2.1</h2>
<p>MySQL Server: <strong>8.0.35</strong> | Protocol: <strong>10</strong></p>
<p>Server charset: <strong>utf8mb4_unicode_ci</strong></p>
<table border="1" cellpadding="5" style="border-collapse:collapse;width:100%">
<tr style="background:#2962ff;color:#fff"><th>Database</th><th>Tables</th><th>Size</th></tr>
<tr><td>brahmastra_prod</td><td>5</td><td>42.7 MB</td></tr>
<tr><td>information_schema</td><td>79</td><td>0 B</td></tr></table></div></body></html>"""

    def _fake_db_dump(self) -> str:
        return """-- MySQL dump 10.13  Distrib 8.0.35, for Linux (x86_64)
-- Host: rds-prod-db.c7abc123.us-east-1.rds.amazonaws.com
-- Database: brahmastra_prod
-- Generation Time: Mar 05, 2026 at 04:30 PM
-- Server version: 8.0.35

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;

-- Table structure for table `users`
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `email` varchar(255) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `full_name` varchar(100) DEFAULT NULL,
  `role` enum('admin','user','moderator') DEFAULT 'user',
  `api_key` varchar(64) DEFAULT NULL,
  `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Dumping data for table `users`
INSERT INTO `users` VALUES (1,'admin@brahmastra.io','$2b$12$HONEYPOT.FAKE.HASH.DO.NOT.USE','System Admin','admin','bk_live_HONEYPOT_FAKE_KEY_001','2024-01-15 08:30:00');
INSERT INTO `users` VALUES (2,'dev@brahmastra.io','$2b$12$ANOTHER.FAKE.HASH.EVIDENCE','Dev User','moderator','bk_live_HONEYPOT_FAKE_KEY_002','2024-02-20 12:00:00');

COMMIT;
"""

    def _fake_config(self) -> str:
        return json.dumps({
            "app": {"name": "Brahmastra", "version": "3.2.1", "environment": "production"},
            "database": {
                "host": "rds-prod-db.c7abc123.us-east-1.rds.amazonaws.com",
                "port": 3306, "name": "brahmastra_prod",
                "username": "admin_readonly",
                "password": "Pr0d_S3cur3_2024!xK9m"
            },
            "redis": {"host": "redis-prod.abc123.cache.amazonaws.com", "port": 6379},
            "aws": {
                "region": "us-east-1",
                "s3_bucket": "brahmastra-data-prod",
                "access_key": "AKIAIOSFODNN7HONEYPOT"
            },
            "jwt": {"secret": "HONEYPOT_JWT_SECRET_DO_NOT_USE", "expiry": 86400},
            "api_keys": ["sk_live_HONEYPOT_001", "sk_live_HONEYPOT_002"]
        }, indent=2)

    def _fake_admin_panel(self) -> str:
        return """<!DOCTYPE html>
<html><head><title>Admin Dashboard - Brahmastra</title>
<style>body{margin:0;font-family:sans-serif;background:#1a1a2e;color:#eee}
.header{background:#16213e;padding:15px 30px;border-bottom:1px solid #0f3460}
.header h1{margin:0;color:#e94560;font-size:20px}
.content{padding:30px;max-width:1200px;margin:0 auto}
.card{background:#16213e;border-radius:12px;padding:20px;margin:10px 0;border:1px solid #0f3460}
.stat{display:inline-block;width:200px;text-align:center;padding:20px}
.stat .number{font-size:32px;font-weight:bold;color:#e94560}.stat .label{color:#888;font-size:12px}
table{width:100%;border-collapse:collapse;margin-top:20px}
th{background:#0f3460;padding:12px;text-align:left}
td{padding:10px;border-bottom:1px solid #0f3460}</style></head>
<body><div class="header"><h1>⚡ Brahmastra Admin Panel</h1></div>
<div class="content">
<div class="card">
<div class="stat"><div class="number">2,847</div><div class="label">Total Users</div></div>
<div class="stat"><div class="number">$127K</div><div class="label">Monthly Revenue</div></div>
<div class="stat"><div class="number">99.9%</div><div class="label">Uptime</div></div>
<div class="stat"><div class="number">12</div><div class="label">API Keys Active</div></div></div>
<div class="card"><h3>Recent Users</h3>
<table><tr><th>ID</th><th>Email</th><th>Role</th><th>API Key</th><th>Status</th></tr>
<tr><td>1</td><td>admin@brahmastra.io</td><td>admin</td><td>bk_live_***001</td><td style="color:#4caf50">Active</td></tr>
<tr><td>2</td><td>cto@brahmastra.io</td><td>admin</td><td>bk_live_***002</td><td style="color:#4caf50">Active</td></tr>
<tr><td>3</td><td>dev@brahmastra.io</td><td>moderator</td><td>bk_live_***003</td><td style="color:#4caf50">Active</td></tr></table></div></div></body></html>"""

    def _fake_user_data(self) -> str:
        return json.dumps({
            "status": "success",
            "total": 2847,
            "page": 1,
            "data": [
                {"id": 1, "email": "admin@brahmastra.io", "name": "System Admin",
                 "role": "admin", "api_key": "bk_live_HONEYPOT_001", "status": "active"},
                {"id": 2, "email": "cto@brahmastra.io", "name": "CTO",
                 "role": "admin", "api_key": "bk_live_HONEYPOT_002", "status": "active"},
                {"id": 3, "email": "dev@brahmastra.io", "name": "Dev Lead",
                 "role": "moderator", "api_key": "bk_live_HONEYPOT_003", "status": "active"},
            ]
        }, indent=2)

    def _fake_server_error(self) -> str:
        return """<!DOCTYPE html>
<html><head><title>500 Internal Server Error</title></head>
<body><h1>Internal Server Error</h1>
<p>The server encountered an unexpected condition.</p>
<pre>Traceback (most recent call last):
  File "/app/main.py", line 342, in handle_request
    result = db.query(User).filter_by(id=request.user_id).first()
  File "/app/database.py", line 89, in query
    return session.execute(stmt)
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at "rds-prod-db.c7abc123.us-east-1.rds.amazonaws.com" refused
</pre>
<hr><address>Apache/2.4.52 (Ubuntu) Server at brahmastra.io Port 443</address></body></html>"""

    # ── Session Management ────────────────────────────────────────────────────

    def _get_or_create_session(self, ip: str, now: datetime) -> AttackerSession:
        """Get existing session or create new one for this IP."""
        if ip not in self._sessions:
            session_id = hashlib.sha256(f"{ip}-{now.isoformat()}".encode()).hexdigest()[:16]
            self._sessions[ip] = AttackerSession(
                session_id=session_id,
                ip=ip,
                first_seen=now.isoformat(),
                last_seen=now.isoformat(),
            )
            self._total_trapped += 1
            logger.warning(f"🍯 NEW ATTACKER SESSION: {ip} (Session: {session_id})")
        return self._sessions[ip]

    def _detect_tools(self, user_agent: str, session: AttackerSession):
        """Detect attack tools from User-Agent."""
        ua_lower = user_agent.lower()
        tool_signatures = {
            "sqlmap": "SQLMap",
            "nikto": "Nikto",
            "nmap": "Nmap",
            "masscan": "Masscan",
            "dirbuster": "DirBuster",
            "gobuster": "GoBuster",
            "wpscan": "WPScan",
            "burp": "Burp Suite",
            "metasploit": "Metasploit",
            "hydra": "Hydra",
            "curl": "cURL",
            "wget": "Wget",
            "python-requests": "Python Requests",
            "python-urllib": "Python urllib",
        }
        for sig, name in tool_signatures.items():
            if sig in ua_lower:
                session.tools_detected.add(name)

    def _assess_severity(self, session: AttackerSession, ai_score: float) -> str:
        """Assess severity of the attacker session."""
        score = 0

        # Based on action count
        if session.total_requests > 50:
            score += 30
        elif session.total_requests > 20:
            score += 20
        elif session.total_requests > 5:
            score += 10

        # Based on attack types
        score += len(session.attack_types) * 10

        # Based on tools detected
        if session.tools_detected:
            score += 20

        # Based on payloads captured
        if session.payloads_captured:
            score += 15

        # Based on AI score
        score += ai_score * 0.3

        if score >= 80:
            return "critical"
        elif score >= 50:
            return "high"
        elif score >= 25:
            return "medium"
        return "low"

    # ── Evidence Collection ───────────────────────────────────────────────────

    def _save_evidence(self, session: AttackerSession):
        """Save forensic evidence for a session to disk."""
        try:
            filename = f"evidence_{session.session_id}_{session.ip.replace('.', '_')}.json"
            filepath = self._evidence_dir / filename

            evidence = {
                "report_type": "FORENSIC_EVIDENCE",
                "generated_at": datetime.now().isoformat(),
                "brahmastra_version": "1.0",
                "attacker_profile": {
                    "session_id": session.session_id,
                    "ip_address": session.ip,
                    "first_seen": session.first_seen,
                    "last_seen": session.last_seen,
                    "total_requests": session.total_requests,
                    "severity": session.severity,
                    "attack_types": list(session.attack_types),
                    "tools_detected": list(session.tools_detected),
                },
                "timeline": [
                    {
                        "timestamp": a.timestamp,
                        "method": a.method,
                        "path": a.path,
                        "response_type": a.response_type,
                        "user_agent": a.user_agent,
                        "headers": a.headers,
                        "body_preview": a.body[:500] if a.body else "",
                    }
                    for a in session.actions
                ],
                "paths_attempted": session.paths_attempted,
                "payloads_captured": [p[:500] for p in session.payloads_captured[:20]],
                "evidence_hash": hashlib.sha256(
                    json.dumps(session.paths_attempted).encode()
                ).hexdigest(),
            }

            with open(filepath, "w") as f:
                json.dump(evidence, f, indent=2)

            session.evidence_saved = True
            self._total_evidence_collected += 1

            logger.warning(
                f"📁 EVIDENCE SAVED: {filename} "
                f"({session.total_requests} actions, severity: {session.severity})"
            )
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to save evidence: {e}")
            return None

    def save_all_evidence(self) -> List[str]:
        """Force save evidence for all active sessions."""
        saved = []
        with self._lock:
            for session in self._sessions.values():
                if session.actions:
                    result = self._save_evidence(session)
                    if result:
                        saved.append(result)
        return saved

    # ── Stats & Reporting ─────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Get honeypot statistics."""
        with self._lock:
            active = [s for s in self._sessions.values() if s.total_requests > 0]
            severity_counts = defaultdict(int)
            all_tools = set()
            all_types = set()

            for s in active:
                severity_counts[s.severity] += 1
                all_tools.update(s.tools_detected)
                all_types.update(s.attack_types)

            return {
                "total_trapped": self._total_trapped,
                "active_sessions": len(active),
                "evidence_collected": self._total_evidence_collected,
                "severity_breakdown": dict(severity_counts),
                "tools_detected": list(all_tools),
                "attack_types": list(all_types),
                "active_attackers": [
                    {
                        "ip": s.ip,
                        "session_id": s.session_id,
                        "requests": s.total_requests,
                        "severity": s.severity,
                        "first_seen": s.first_seen,
                        "tools": list(s.tools_detected),
                    }
                    for s in sorted(active, key=lambda x: x.total_requests, reverse=True)[:10]
                ],
            }

    def get_session(self, ip: str) -> Optional[Dict]:
        """Get detailed session info for an IP."""
        with self._lock:
            if ip not in self._sessions:
                return None
            s = self._sessions[ip]
            return {
                "session_id": s.session_id,
                "ip": s.ip,
                "first_seen": s.first_seen,
                "last_seen": s.last_seen,
                "total_requests": s.total_requests,
                "severity": s.severity,
                "attack_types": list(s.attack_types),
                "tools_detected": list(s.tools_detected),
                "paths_attempted": s.paths_attempted[-20:],
                "recent_actions": [
                    {
                        "timestamp": a.timestamp,
                        "method": a.method,
                        "path": a.path,
                        "response_type": a.response_type,
                    }
                    for a in s.actions[-10:]
                ],
                "evidence_saved": s.evidence_saved,
            }

    def _cleanup_loop(self):
        """Clean up expired sessions."""
        while True:
            time.sleep(300)
            try:
                now = time.time()
                with self._lock:
                    expired = []
                    for ip, s in self._sessions.items():
                        last = datetime.fromisoformat(s.last_seen).timestamp()
                        if now - last > SESSION_TIMEOUT:
                            # Save evidence before cleanup
                            if s.actions and not s.evidence_saved:
                                self._save_evidence(s)
                            expired.append(ip)
                    for ip in expired:
                        del self._sessions[ip]
                    if expired:
                        logger.info(f"🧹 Cleaned {len(expired)} expired honeypot sessions")
            except Exception as e:
                logger.error(f"Honeypot cleanup error: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────
honeypot_engine = HoneypotEngine()

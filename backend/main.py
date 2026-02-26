import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import psutil
import asyncio
import os

from fastapi import FastAPI, WebSocket, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.logger import get_logger

logger = get_logger("brahmastra.backend")

# ── DB Import ─────────────────────────────────────────────────────────────────
from backend.database import get_db, engine, Base
from backend.models import Metric, ThreatScore, SystemEvent, User
from backend.schemas import (
    MetricResponse,
    ThreatScoreResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    Token,
    RefreshToken,
    PasswordResetRequest,
    PasswordResetConfirm,
)
from backend.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    get_current_user_email,
)
DB_ENABLED = True

# ── Threat Detection + Email ──────────────────────────────────────────────────
try:
    from backend.threat_detection import threat_engine, MAX_FAILED_LOGINS
    from backend.email_service import email_service
    THREAT_ENGINE_ENABLED = True
except ImportError as e:
    THREAT_ENGINE_ENABLED = False
    logger.warning(f"⚠️ Threat engine not available: {e}")

# ── Alerts (Slack/Telegram) + ML Anomaly Detection ───────────────────────────
try:
    from backend.alerts import alert_service
    ALERTS_ENABLED = True
except ImportError:
    ALERTS_ENABLED = False
    logger.warning("⚠️ Alert service not available")

try:
    from backend.anomaly_detection import anomaly_detector
    ANOMALY_ENABLED = True
except ImportError:
    ANOMALY_ENABLED = False
    logger.warning("⚠️ Anomaly detection not available")

# ── Rate Limiter ──────────────────────────────────────────────────────────────
try:
    from backend.rate_limiter import rate_limiter
    RATE_LIMITER_ENABLED = True
except ImportError:
    RATE_LIMITER_ENABLED = False
    logger.warning("⚠️ Rate limiter not available")

# ── Backup System ────────────────────────────────────────────────────────────
try:
    from backend.backup_system import backup_manager
    BACKUP_ENABLED = True
except ImportError:
    BACKUP_ENABLED = False
    logger.warning("⚠️ Backup system not available")

# ── Performance Tracker ──────────────────────────────────────────────────────
try:
    from backend.performance import perf_tracker
    PERF_ENABLED = True
except ImportError:
    PERF_ENABLED = False
    logger.warning("⚠️ Performance tracker not available")

# ── Config ────────────────────────────────────────────────────────────────────
SERVER_HOST = os.getenv("SERVER_HOST", "http://15.206.82.159")
_cors_raw = os.getenv(
    "CORS_ORIGINS",
    f"{SERVER_HOST},{SERVER_HOST}:8080,http://localhost:8080,http://127.0.0.1:8080",
)
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Brahmastra API",
    description="Self-Healing Infrastructure Monitoring System",
    version="0.3.0",
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── IP Ban Middleware ─────────────────────────────────────────────────────────
@app.middleware("http")
async def ip_ban_middleware(request: Request, call_next):
    """Block requests from banned IPs before they hit any endpoint."""
    if THREAT_ENGINE_ENABLED:
        client_ip = request.client.host if request.client else "unknown"
        is_banned, seconds_left = threat_engine.is_ip_banned(client_ip)
        if is_banned:
            logger.warning(f"🚫 Blocked request from banned IP: {client_ip} ({seconds_left}s remaining)")
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Your IP is temporarily blocked due to too many failed login attempts. "
                              f"Try again in {seconds_left // 60 + 1} minutes.",
                    "ban_expires_in_seconds": seconds_left,
                },
            )
    # ── Rate Limiting ──
    if RATE_LIMITER_ENABLED:
        client_ip = request.client.host if request.client else "unknown"
        category = rate_limiter.classify_request(str(request.url.path), request.method)
        allowed, info = rate_limiter.check(client_ip, category)
        if not allowed:
            logger.warning(f"🚦 Rate limited: {client_ip} ({category}) - retry in {info['retry_after']}s")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down.",
                    "retry_after": info["retry_after"],
                    "category": info["category"],
                    "limit": info["limit"],
                },
                headers={"Retry-After": str(info["retry_after"])},
            )

    # ── Performance Tracking ──
    if PERF_ENABLED:
        import time as _time
        _start = _time.time()

    response = await call_next(request)

    if PERF_ENABLED:
        duration_ms = (_time.time() - _start) * 1000
        perf_tracker.record(
            request.method,
            str(request.url.path),
            response.status_code,
            duration_ms,
        )

    return response


# ── Global Exception Handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    logger.error(f"❌ Unhandled error: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers={"Access-Control-Allow-Origin": "*"},
    )


# In-memory fallback
incidents: List[Dict] = []
metrics_history: List[Dict] = []


class HealthStatus(BaseModel):
    status: str
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    timestamp: str


class Incident(BaseModel):
    id: int
    type: str
    severity: int
    description: str
    timestamp: str
    resolved: bool


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Brahmastra v0.4.0 Starting...")
    logger.info(f"   SERVER_HOST     : {SERVER_HOST}")
    logger.info(f"   CORS_ORIGINS    : {CORS_ORIGINS}")
    logger.info(f"   DB_ENABLED      : {DB_ENABLED}")
    logger.info(f"   THREAT_ENGINE   : {THREAT_ENGINE_ENABLED}")
    logger.info(f"   RATE_LIMITER    : {RATE_LIMITER_ENABLED}")
    logger.info(f"   BACKUP_SYSTEM   : {BACKUP_ENABLED}")
    logger.info(f"   PERF_TRACKER    : {PERF_ENABLED}")
    if DB_ENABLED:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("✅ Database tables verified")
        except Exception as e:
            logger.error(f"❌ Table creation failed: {e}")
    # Start backup scheduler
    if BACKUP_ENABLED:
        backup_manager.start_scheduler()
        logger.info("✅ Backup scheduler started")


# ── Root + Health (Public) ────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "app": "Brahmastra",
        "version": "0.3.0",
        "status": "running",
        "database": "enabled" if DB_ENABLED else "disabled",
        "threat_engine": "enabled" if THREAT_ENGINE_ENABLED else "disabled",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ============================================================================
# AUTH ENDPOINTS
# ============================================================================

@app.post("/api/auth/register", response_model=UserResponse)
@limiter.limit("5/minute")
async def register(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="Database not available")

    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # First user in the system is auto-admin
    user_count = db.query(User).count()
    verification_token = str(uuid.uuid4())
    db_user = User(
        email=user.email,
        hashed_password=get_password_hash(user.password),
        full_name=user.full_name,
        verification_token=verification_token,
        is_verified=False,
        is_admin=(user_count == 0),  # First user = admin
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    verify_link = f"{SERVER_HOST}/verify-email.html?token={verification_token}"
    if THREAT_ENGINE_ENABLED:
        await email_service.send_verification_email(user.email, verify_link)
    else:
        logger.info(f"📧 [MOCK] Verify link for {user.email}: {verify_link}")

    logger.info(f"✅ User registered: {user.email}")
    return db_user


@app.get("/api/auth/verify-email")
async def verify_email(token: str, db: Session = Depends(get_db)):
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="Database not available")
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    if user.is_verified:
        return {"message": "Email already verified"}
    user.is_verified = True
    user.verification_token = None
    db.commit()
    logger.info(f"✅ Email verified: {user.email}")
    return {"message": "Email verified successfully"}


@app.post("/api/auth/login", response_model=Token)
@limiter.limit("10/minute")
async def login(request: Request, user: UserLogin, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="Database not available")

    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        logger.warning(f"❌ Failed login: {user.email} from {client_ip}")
        # Track failed attempt for IP banning
        if THREAT_ENGINE_ENABLED:
            was_banned = threat_engine.record_failed_login(client_ip)
            if was_banned:
                # Log security event
                if DB_ENABLED:
                    try:
                        db_event = SystemEvent(
                            event_type="ip_banned",
                            description=f"IP {client_ip} auto-banned after repeated failed logins",
                            severity="high",
                        )
                        db.add(db_event)
                        db.commit()
                    except Exception:
                        db.rollback()
                # 🚨 Auto-email security alert to admin
                if THREAT_ENGINE_ENABLED:
                    try:
                        admin_email = None
                        if DB_ENABLED and db:
                            admin = db.query(User).filter(User.is_active == True).first()
                            if admin:
                                admin_email = admin.email
                        if admin_email:
                            await email_service.send_security_alert(
                                admin_email,
                                f"IP {client_ip} was automatically banned after {MAX_FAILED_LOGINS} failed login attempts in 5 minutes.",
                                client_ip,
                            )
                    except Exception as e:
                        logger.error(f"⚠️ Could not send ban alert email: {e}")
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not db_user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    # Clear failed login record on success
    if THREAT_ENGINE_ENABLED:
        threat_engine.record_successful_login(client_ip)

    access_token = create_access_token(data={"sub": db_user.email})
    refresh_token = create_refresh_token(data={"sub": db_user.email})

    logger.info(f"✅ Login: {user.email} from {client_ip}")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
        "expires_in": 1800,
    }


@app.post("/api/auth/refresh", response_model=Token)
async def refresh_token(data: RefreshToken):
    """Exchange a valid refresh token for a new access token."""
    email = verify_refresh_token(data.refresh_token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    new_access = create_access_token(data={"sub": email})
    new_refresh = create_refresh_token(data={"sub": email})
    return {
        "access_token": new_access,
        "token_type": "bearer",
        "refresh_token": new_refresh,
        "expires_in": 1800,
    }


@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="Database not available")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.post("/api/auth/logout")
async def logout(email: str = Depends(get_current_user_email)):
    logger.info(f"👋 Logout: {email}")
    return {"message": "Logged out successfully"}


# ── Password Reset ────────────────────────────────────────────────────────────
@app.post("/api/auth/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: PasswordResetRequest, db: Session = Depends(get_db)):
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="Database not available")
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        return {"message": "If this email is registered, you will receive a reset link."}

    token = str(uuid.uuid4())
    user.reset_token = token
    user.reset_token_expiry = datetime.now() + timedelta(minutes=30)
    db.commit()

    reset_link = f"{SERVER_HOST}/reset-password.html?token={token}"
    if THREAT_ENGINE_ENABLED:
        await email_service.send_password_reset_email(data.email, reset_link)
    else:
        logger.info(f"📧 [MOCK] Reset link for {data.email}: {reset_link}")

    return {"message": "If this email is registered, you will receive a reset link."}


@app.post("/api/auth/reset-password")
async def reset_password(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="Database not available")
    user = db.query(User).filter(User.reset_token == data.token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if user.reset_token_expiry.replace(tzinfo=None) < datetime.now():
        raise HTTPException(status_code=400, detail="Token has expired")
    user.hashed_password = get_password_hash(data.new_password)
    user.reset_token = None
    user.reset_token_expiry = None
    db.commit()
    logger.info(f"✅ Password reset: {user.email}")
    return {"message": "Password reset successfully. You can now login."}


# ============================================================================
# METRICS ENDPOINTS (JWT Protected)
# ============================================================================

@app.get("/api/metrics/current", response_model=HealthStatus)
async def get_current_metrics(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db) if DB_ENABLED else None,
):
    """Get current system metrics. Requires authentication."""
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    status_str = "healthy" if cpu < 80 and memory < 80 else "warning"
    metrics = {"status": status_str, "cpu_percent": cpu, "memory_percent": memory,
               "disk_percent": disk, "timestamp": datetime.now().isoformat()}

    if DB_ENABLED and db:
        try:
            db.add(Metric(cpu_percent=cpu, memory_percent=memory, disk_percent=disk, status=status_str))
            db.commit()
        except Exception as e:
            logger.error(f"❌ Metric save failed: {e}")
            db.rollback()
    else:
        metrics_history.append(metrics)
        if len(metrics_history) > 1000:
            metrics_history.pop(0)
    return metrics


@app.get("/api/metrics/history")
async def get_metrics_history(
    limit: int = 100,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db) if DB_ENABLED else None,
):
    """Get historical metrics. Requires authentication."""
    if DB_ENABLED and db:
        try:
            rows = db.query(Metric).order_by(Metric.timestamp.desc()).limit(limit).all()
            return [{"id": m.id, "cpu_percent": m.cpu_percent, "memory_percent": m.memory_percent,
                     "disk_percent": m.disk_percent, "status": m.status,
                     "timestamp": m.timestamp.isoformat()} for m in reversed(rows)]
        except Exception as e:
            logger.error(f"❌ Metrics history failed: {e}")
            return []
    return metrics_history[-limit:]


# ============================================================================
# THREAT ENDPOINTS (JWT Protected)
# ============================================================================

@app.get("/api/threat/score")
async def get_threat_score(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db) if DB_ENABLED else None,
):
    """Get threat score. Uses advanced multi-factor calculation. Requires auth."""
    if THREAT_ENGINE_ENABLED:
        result = threat_engine.calculate_threat_score()
    else:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent
        score = int((cpu + memory) / 2)
        level = "low" if score < 50 else "medium" if score < 80 else "high"
        result = {"threat_score": score, "level": level, "timestamp": datetime.now().isoformat()}

    if DB_ENABLED and db:
        try:
            db.add(ThreatScore(threat_score=result["threat_score"], threat_level=result["level"]))
            db.commit()
        except Exception as e:
            logger.error(f"❌ ThreatScore save failed: {e}")
            db.rollback()
    return result


@app.get("/api/threat/history")
async def get_threat_history(
    limit: int = 100,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db) if DB_ENABLED else None,
):
    if DB_ENABLED and db:
        try:
            rows = db.query(ThreatScore).order_by(ThreatScore.timestamp.desc()).limit(limit).all()
            return [{"id": s.id, "threat_score": s.threat_score, "threat_level": s.threat_level,
                     "timestamp": s.timestamp.isoformat()} for s in reversed(rows)]
        except Exception as e:
            logger.error(f"❌ Threat history failed: {e}")
    return []


@app.get("/api/threat/blocked-ips")
async def get_blocked_ips(email: str = Depends(get_current_user_email)):
    """Get list of currently banned IPs. Requires authentication."""
    if not THREAT_ENGINE_ENABLED:
        return {"blocked": [], "message": "Threat engine not available"}
    return {"blocked": threat_engine.get_blocked_ips()}


@app.delete("/api/threat/blocked-ips/{ip}")
async def unblock_ip(ip: str, email: str = Depends(get_current_user_email)):
    """Manually unblock an IP. Requires authentication."""
    if not THREAT_ENGINE_ENABLED:
        raise HTTPException(status_code=503, detail="Threat engine not available")
    success = threat_engine.unblock_ip(ip)
    if not success:
        raise HTTPException(status_code=404, detail="IP not found in ban list")
    return {"message": f"IP {ip} unblocked"}


# ============================================================================
# HONEYPOT ENDPOINTS — Attacker Traps 🍯
# ============================================================================

HONEYPOT_PATHS = ["/admin", "/wp-admin", "/phpmyadmin", "/.env",
                  "/wp-login.php", "/xmlrpc.php", "/.git/config",
                  "/config.php", "/administrator", "/manager"]


async def _handle_honeypot(request: Request, path: str, db: Session):
    """Common handler for all honeypot endpoints."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    if THREAT_ENGINE_ENABLED:
        threat_engine.record_honeypot_hit(client_ip, path, user_agent)

    # Log to DB
    if DB_ENABLED and db:
        try:
            db.add(SystemEvent(
                event_type="honeypot_hit",
                description=f"Honeypot triggered: {path} from {client_ip}",
                severity="high",
            ))
            db.commit()
        except Exception:
            db.rollback()

    # Return convincing fake response to waste attacker's time
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "message": "Welcome"},
    )


@app.get("/admin")
@app.get("/wp-admin")
@app.get("/wp-admin/")
@app.get("/phpmyadmin")
@app.get("/wp-login.php")
@app.get("/xmlrpc.php")
@app.get("/.env")
@app.get("/.git/config")
@app.get("/config.php")
@app.get("/administrator")
async def honeypot(request: Request, db: Session = Depends(get_db) if DB_ENABLED else None):
    """🍯 Honeypot — logs attacker IPs."""
    return await _handle_honeypot(request, str(request.url.path), db)


@app.get("/api/honeypot/stats")
async def honeypot_stats(email: str = Depends(get_current_user_email)):
    """Get honeypot hit statistics. Requires authentication."""
    if not THREAT_ENGINE_ENABLED:
        return {"total_hits": 0, "message": "Threat engine not available"}
    return threat_engine.get_honeypot_stats()


@app.get("/api/honeypot/hits")
async def honeypot_hits(
    limit: int = 50,
    email: str = Depends(get_current_user_email),
):
    """Get recent honeypot hits. Requires authentication."""
    if not THREAT_ENGINE_ENABLED:
        return []
    return threat_engine.get_honeypot_hits(limit=limit)


# ============================================================================
# EVENTS ENDPOINTS (JWT Protected)
# ============================================================================

@app.get("/api/events")
async def get_events(
    limit: int = 50,
    event_type: Optional[str] = None,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db) if DB_ENABLED else None,
):
    if DB_ENABLED and db:
        try:
            query = db.query(SystemEvent)
            if event_type:
                query = query.filter(SystemEvent.event_type == event_type)
            rows = query.order_by(SystemEvent.timestamp.desc()).limit(limit).all()
            return [{"id": e.id, "event_type": e.event_type, "description": e.description,
                     "severity": e.severity, "timestamp": e.timestamp.isoformat()}
                    for e in reversed(rows)]
        except Exception as e:
            logger.error(f"❌ Events fetch failed: {e}")
            return []
    return []


# ============================================================================
# STATS (Public — used by dashboard before login to show summary)
# ============================================================================

@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db) if DB_ENABLED else None):
    """Aggregate stats for dashboard. Public endpoint."""
    honeypot_count = 0
    blocked_ip_count = 0
    if THREAT_ENGINE_ENABLED:
        honeypot_count = threat_engine.get_honeypot_stats().get("total_hits", 0)
        blocked_ip_count = len(threat_engine.get_blocked_ips())

    if not DB_ENABLED or not db:
        return {
            "database": "disabled",
            "metrics_count": len(metrics_history),
            "threats_count": 0,
            "events_count": 0,
            "users_count": 0,
            "honeypot_hits": honeypot_count,
            "blocked_ips": blocked_ip_count,
        }
    try:
        return {
            "database": "enabled",
            "metrics_count": db.query(Metric).count(),
            "threats_count": db.query(ThreatScore).count(),
            "events_count": db.query(SystemEvent).count(),
            "users_count": db.query(User).count(),
            "honeypot_hits": honeypot_count,
            "blocked_ips": blocked_ip_count,
        }
    except Exception as e:
        logger.error(f"❌ Stats failed: {e}")
        return {"database": "error", "error": str(e)}


# ============================================================================
# INCIDENTS (Legacy in-memory)
# ============================================================================

@app.get("/api/incidents", response_model=List[Incident])
async def get_incidents(
    limit: int = 50,
    email: str = Depends(get_current_user_email),
):
    return incidents[-limit:]


@app.post("/api/incidents")
async def create_incident(
    incident: Incident,
    email: str = Depends(get_current_user_email),
):
    incidents.append(incident.dict())
    return {"status": "created", "incident": incident}


# ============================================================================
# KILL SWITCH
# ============================================================================

@app.post("/api/kill-switch")
async def trigger_kill_switch(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db) if DB_ENABLED else None,
):
    # Admin-only check
    if DB_ENABLED and db:
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_admin:
            raise HTTPException(status_code=403, detail="Only admins can trigger the kill switch")
    incident = {
        "id": len(incidents) + 1,
        "type": "manual_kill_switch",
        "severity": 10,
        "description": f"Kill-switch triggered by {email}",
        "timestamp": datetime.now().isoformat(),
        "resolved": False,
    }
    incidents.append(incident)

    if THREAT_ENGINE_ENABLED:
        threat_engine.activate_kill_switch()

    if DB_ENABLED and db:
        try:
            db.add(SystemEvent(
                event_type="kill_switch",
                description=f"Kill-switch triggered by {email}",
                severity="critical",
            ))
            db.commit()
        except Exception:
            db.rollback()

    logger.critical(f"🚨 KILL SWITCH TRIGGERED by {email}")

    # Send Slack/Telegram alert
    if ALERTS_ENABLED:
        await alert_service.alert_kill_switch(email)

    return {"status": "triggered", "message": "Kill-switch activated. Auto-healing in progress...",
            "incident_id": incident["id"]}


@app.post("/api/kill-switch/deactivate")
async def deactivate_kill_switch(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db) if DB_ENABLED else None,
):
    """Deactivate an active kill switch. Admin only."""
    if DB_ENABLED and db:
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_admin:
            raise HTTPException(status_code=403, detail="Only admins can deactivate the kill switch")
    if THREAT_ENGINE_ENABLED:
        threat_engine.deactivate_kill_switch()
    logger.info(f"✅ Kill switch deactivated by {email}")
    return {"status": "deactivated", "message": "Kill switch deactivated."}


# ============================================================================
# ML ANOMALY DETECTION
# ============================================================================

@app.get("/api/anomaly/status")
async def get_anomaly_status(email: str = Depends(get_current_user_email)):
    if not ANOMALY_ENABLED:
        return {"enabled": False, "message": "Anomaly detection not available"}
    return anomaly_detector.get_status()


@app.get("/api/anomaly/history")
async def get_anomaly_history(email: str = Depends(get_current_user_email)):
    if not ANOMALY_ENABLED:
        return []
    return anomaly_detector.get_anomaly_history()


# ============================================================================
# ALERT HISTORY
# ============================================================================

@app.get("/api/alerts/history")
async def get_alert_history(email: str = Depends(get_current_user_email)):
    if not ALERTS_ENABLED:
        return []
    return alert_service.get_alert_history()


@app.get("/api/alerts/status")
async def get_alert_status(email: str = Depends(get_current_user_email)):
    if not ALERTS_ENABLED:
        return {"enabled": False}
    return {
        "enabled": True,
        "slack": alert_service.slack_enabled,
        "telegram": alert_service.telegram_enabled,
        "total_alerts": len(alert_service.alert_history),
    }


# ============================================================================
# WEBSOCKET  (real-time dashboard updates)
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Verify JWT token from query param: /ws?token=xxx
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Token required")
        return
    from backend.auth import verify_token
    email = verify_token(token)
    if not email:
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()
    logger.info(f"🔌 WebSocket connected: {email}")
    try:
        while True:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent
            threat_data = {}
            if THREAT_ENGINE_ENABLED:
                ts = threat_engine.calculate_threat_score()
                threat_data = {
                    "threat_score": ts["threat_score"],
                    "threat_level": ts["level"],
                    "blocked_ips": len(threat_engine.get_blocked_ips()),
                    "honeypot_hits": threat_engine.get_honeypot_stats().get("total_hits", 0),
                }

            # ML Anomaly Detection — feed metrics into detector
            anomaly_data = {}
            if ANOMALY_ENABLED:
                analysis = anomaly_detector.analyze(cpu, memory, disk)
                anomaly_data = {
                    "anomaly_status": analysis["status"],
                    "anomaly_count": analysis.get("total_anomalies", 0),
                }
                # Send alert for any detected anomalies
                if analysis.get("anomalies") and ALERTS_ENABLED:
                    for a in analysis["anomalies"]:
                        await alert_service.alert_anomaly(
                            a["metric"], a["value"], a["expected"], a["z_score"]
                        )

            await websocket.send_json({
                "type": "metrics_update",
                "cpu": cpu,
                "memory": memory,
                "disk": disk,
                "timestamp": datetime.now().isoformat(),
                **threat_data,
                **anomaly_data,
            })
            await asyncio.sleep(5)
    except Exception as e:
        logger.info(f"WebSocket closed ({email}): {e}")


# ============================================================================
# RATE LIMITER ENDPOINTS
# ============================================================================

@app.get("/api/ratelimit/status")
async def ratelimit_status(email: str = Depends(get_current_user_email)):
    """Get rate limiter statistics (admin view)."""
    if not RATE_LIMITER_ENABLED:
        return {"enabled": False}
    return rate_limiter.get_status()


# ============================================================================
# BACKUP ENDPOINTS
# ============================================================================

@app.post("/api/backup/create")
async def create_backup(email: str = Depends(get_current_user_email)):
    """Create a manual backup."""
    if not BACKUP_ENABLED:
        raise HTTPException(status_code=503, detail="Backup system not available")
    result = backup_manager.create_backup(label="manual")
    return result


@app.get("/api/backup/list")
async def list_backups(email: str = Depends(get_current_user_email)):
    """List all available backups."""
    if not BACKUP_ENABLED:
        raise HTTPException(status_code=503, detail="Backup system not available")
    return {"backups": backup_manager.list_backups()}


@app.get("/api/backup/status")
async def backup_status(email: str = Depends(get_current_user_email)):
    """Get backup system status."""
    if not BACKUP_ENABLED:
        return {"enabled": False}
    return backup_manager.get_status()


@app.post("/api/backup/restore/{filename}")
async def restore_backup(filename: str, email: str = Depends(get_current_user_email)):
    """Restore from a specific backup (admin only)."""
    if not BACKUP_ENABLED:
        raise HTTPException(status_code=503, detail="Backup system not available")
    result = backup_manager.restore_backup(filename)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ============================================================================
# PERFORMANCE ENDPOINTS
# ============================================================================

@app.get("/api/performance/stats")
async def performance_stats(email: str = Depends(get_current_user_email)):
    """Get comprehensive performance statistics."""
    if not PERF_ENABLED:
        return {"enabled": False}
    return perf_tracker.get_stats()


@app.get("/api/performance/slow")
async def slow_endpoints(threshold: float = 100, email: str = Depends(get_current_user_email)):
    """Get endpoints with response times above threshold."""
    if not PERF_ENABLED:
        return {"enabled": False, "slow_endpoints": []}
    return {"threshold_ms": threshold, "slow_endpoints": perf_tracker.get_slow_endpoints(threshold)}


@app.get("/api/performance/recent")
async def recent_requests(email: str = Depends(get_current_user_email)):
    """Get recent requests for real-time monitoring."""
    if not PERF_ENABLED:
        return {"enabled": False, "requests": []}
    return {"requests": perf_tracker.get_recent_requests()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

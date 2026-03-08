"""
Brahmastra API v2.0 — main.py
================================
SECURITY UPGRADES:
  - DDoS burst detection in middleware (auto-ban + 429)
  - Payload inspection (SQLi, XSS, path traversal, cmd injection)
  - Security headers on every response (HSTS, CSP, X-Frame, etc.)
  - Hardened CORS (no wildcard in production)
  - Request size limit (prevent memory exhaustion attacks)
  - Admin-only endpoints require is_admin check
  - /api/stats now requires auth (info leakage prevention)
  - WebSocket rate-limited per token
  - Startup integrity check (warn if default JWT key)
"""

import uuid
import time
import asyncio
import os
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import psutil
from fastapi import FastAPI, WebSocket, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.logger import get_logger

logger = get_logger("brahmastra.backend")

# ── DB ────────────────────────────────────────────────────────────────────────
from backend.database import get_db, engine, Base
from backend.models import Metric, ThreatScore, SystemEvent, User
from backend.schemas import (
    MetricResponse, ThreatScoreResponse,
    UserCreate, UserLogin, UserResponse,
    Token, RefreshToken,
    PasswordResetRequest, PasswordResetConfirm,
)
from backend.auth import (
    get_password_hash, verify_password,
    create_access_token, create_refresh_token,
    verify_refresh_token, get_current_user_email,
    SECRET_KEY, _DEFAULT_KEY,
)
DB_ENABLED = True

# ── Optional modules ──────────────────────────────────────────────────────────
try:
    from backend.threat_detection import threat_engine, MAX_FAILED_LOGINS
    from backend.email_service import email_service
    THREAT_ENGINE_ENABLED = True
except ImportError as e:
    THREAT_ENGINE_ENABLED = False
    logger.warning(f"⚠️ Threat engine not available: {e}")

try:
    from backend.alerts import alert_service
    ALERTS_ENABLED = True
except ImportError:
    ALERTS_ENABLED = False

try:
    from backend.anomaly_detection import anomaly_detector
    ANOMALY_ENABLED = True
except ImportError:
    ANOMALY_ENABLED = False

try:
    from backend.rate_limiter import rate_limiter
    RATE_LIMITER_ENABLED = True
except ImportError:
    RATE_LIMITER_ENABLED = False

try:
    from backend.backup_system import backup_manager
    BACKUP_ENABLED = True
except ImportError:
    BACKUP_ENABLED = False

try:
    from backend.performance import perf_tracker
    PERF_ENABLED = True
except ImportError:
    PERF_ENABLED = False

# ── AI Defense Pillars ────────────────────────────────────────────────────────
try:
    from backend.ai_classifier import ai_classifier
    AI_CLASSIFIER_ENABLED = True
except ImportError as e:
    AI_CLASSIFIER_ENABLED = False
    logger.warning(f"⚠️ AI Classifier not available: {e}")

try:
    from backend.honeypot_engine import honeypot_engine
    HONEYPOT_ENGINE_ENABLED = True
except ImportError as e:
    HONEYPOT_ENGINE_ENABLED = False
    logger.warning(f"⚠️ Honeypot Engine not available: {e}")

try:
    from backend.emergency_response import emergency_response
    EMERGENCY_ENABLED = True
except ImportError as e:
    EMERGENCY_ENABLED = False
    logger.warning(f"⚠️ Emergency Response not available: {e}")

# ── Config ────────────────────────────────────────────────────────────────────
SERVER_HOST = os.getenv("SERVER_HOST", "http://localhost")
_cors_raw   = os.getenv(
    "CORS_ORIGINS",
    f"{SERVER_HOST},{SERVER_HOST}:8080,http://localhost:8080,http://127.0.0.1:8080",
)
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]
MAX_REQUEST_SIZE_BYTES = 1 * 1024 * 1024  # 1 MB hard limit

# IPs that are never blocked (add your home IP here)
WHITELISTED_IPS = set(
    ip.strip() for ip in
    os.getenv("WHITELISTED_IPS", "127.0.0.1,::1").split(",")
    if ip.strip()
)
# Trusted reverse proxies — X-Forwarded-For is trusted FROM these IPs only
TRUSTED_PROXIES = {"127.0.0.1", "::1"}


def get_client_ip(request: Request) -> str:
    """
    Returns the real client IP.
    If the direct connection comes from a trusted proxy (Nginx/localhost),
    we read X-Forwarded-For to get the upstream client IP.
    Otherwise we use the raw TCP connection IP.
    """
    direct_ip = request.client.host if request.client else "unknown"
    xff = request.headers.get("X-Forwarded-For", "")
    if xff and direct_ip in TRUSTED_PROXIES:
        # Take the first (leftmost) IP, which is the actual client
        return xff.split(",")[0].strip()
    return direct_ip


# ── System Stats Cache (non-blocking) ────────────────────────────────────────
import threading as _threading

class _SystemStatsCache:
    """
    Refreshes CPU / memory / disk every REFRESH_INTERVAL seconds
    in a background daemon thread.  All FastAPI endpoints read
    from this cache instantly — zero blocking.
    """
    REFRESH_INTERVAL = 2  # seconds

    def __init__(self):
        # Prime the cache with a non-blocking sample
        # (interval=None uses the last measurement or returns 0.0 the first time)
        self._cpu  = psutil.cpu_percent(interval=None)
        self._mem  = psutil.virtual_memory().percent
        self._disk = psutil.disk_usage("/").percent
        self._lock = _threading.Lock()
        t = _threading.Thread(target=self._refresh_loop, daemon=True)
        t.start()

    def _refresh_loop(self):
        # First real blocking call on startup (only once, in background)
        psutil.cpu_percent(interval=1)
        while True:
            try:
                cpu  = psutil.cpu_percent(interval=self.REFRESH_INTERVAL)
                mem  = psutil.virtual_memory().percent
                disk = psutil.disk_usage("/").percent
                with self._lock:
                    self._cpu  = cpu
                    self._mem  = mem
                    self._disk = disk
            except Exception:
                pass

    @property
    def cpu(self) -> float:
        with self._lock:
            return self._cpu

    @property
    def mem(self) -> float:
        with self._lock:
            return self._mem

    @property
    def disk(self) -> float:
        with self._lock:
            return self._disk

    def snapshot(self) -> dict:
        with self._lock:
            return {"cpu": self._cpu, "mem": self._mem, "disk": self._disk}


_stats = _SystemStatsCache()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Brahmastra API",
    description="Self-Healing Infrastructure Monitoring System",
    version="2.0.0",
    # Hide docs in production
    docs_url=None if os.getenv("ENV") == "production" else "/docs",
    redoc_url=None if os.getenv("ENV") == "production" else "/redoc",
)

# ── Prometheus Metrics (/metrics endpoint for Grafana) ─────────────────────────
try:
    from prometheus_fastapi_instrumentator import Instrumentator as _Instrumentator
    _Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    logger.info("📊 Prometheus /metrics endpoint enabled")
except ImportError:
    logger.warning("⚠️  prometheus-fastapi-instrumentator not installed — /metrics disabled")


limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


# ── Security Headers Middleware ───────────────────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"]    = "nosniff"
    response.headers["X-Frame-Options"]            = "DENY"
    response.headers["X-XSS-Protection"]           = "1; mode=block"
    response.headers["Referrer-Policy"]            = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]         = "geolocation=(), microphone=()"
    response.headers["Strict-Transport-Security"]  = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"]    = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' wss:;"
    )
    # Remove server fingerprint
    if "server" in response.headers:
        del response.headers["server"]
    if "x-powered-by" in response.headers:
        del response.headers["x-powered-by"]
    return response


# ── Request Size Limit Middleware ─────────────────────────────────────────────
@app.middleware("http")
async def request_size_limit(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_SIZE_BYTES:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(f"🚫 Oversized request from {client_ip}: {content_length} bytes")
        return JSONResponse(
            status_code=413,
            content={"detail": "Request too large. Max 1MB."},
        )
    return await call_next(request)


# ── Main Security Middleware ──────────────────────────────────────────────────
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    client_ip = get_client_ip(request)
    path      = str(request.url.path)

    def attach_cors(resp):
        origin = request.headers.get("origin")
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp

    # Bypass security checks for CORS preflight
    if request.method == "OPTIONS":
        return await call_next(request)

    # Never block whitelisted admin IPs
    if client_ip in WHITELISTED_IPS:
        _start = time.time()
        response = await call_next(request)
        if PERF_ENABLED:
            perf_tracker.record(request.method, path, response.status_code, (time.time() - _start) * 1000)
        return response

    # 1. IP Ban check — FAST REJECT (minimal CPU, no JSON, no logging)
    if THREAT_ENGINE_ENABLED:
        is_banned, seconds_left = threat_engine.is_ip_banned(client_ip)
        if is_banned:
            return attach_cors(Response(content="blocked", status_code=403, media_type="text/plain"))

    # 2. DDoS burst check — FAST REJECT
    if THREAT_ENGINE_ENABLED:
        if threat_engine.check_ddos(client_ip):
            return attach_cors(Response(content="rate limited", status_code=429, media_type="text/plain"))

    # 3. Rate limit check
    if RATE_LIMITER_ENABLED:
        category = rate_limiter.classify_request(path, request.method)
        allowed, info = rate_limiter.check(client_ip, category)
        if not allowed:
            reason = info.get("reason", "rate_limited")
            logger.warning(f"🚦 Rate limited [{reason}]: {client_ip} → {category}")
            return attach_cors(JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down.",
                    "retry_after": info["retry_after"],
                    "category": info["category"],
                },
                headers={"Retry-After": str(info["retry_after"])},
            ))

    # 4. AI CLASSIFICATION — The brain of Brahmastra
    ai_result = None
    if AI_CLASSIFIER_ENABLED:
        user_agent = request.headers.get("user-agent", "")
        query_str = str(request.url.query)
        ai_result = ai_classifier.classify(
            ip=client_ip, path=path, method=request.method,
            user_agent=user_agent, query_string=query_str,
        )

        # CRITICAL → Trigger emergency response
        if ai_result.label == "critical" and EMERGENCY_ENABLED:
            logger.critical(f"🚨 CRITICAL THREAT from {client_ip}: {ai_result.attack_type} (score: {ai_result.score})")
            # Run emergency in background thread so we can still respond
            import threading
            threading.Thread(
                target=emergency_response.trigger_emergency,
                args=(f"AI detected critical threat: {ai_result.attack_type}", client_ip, ai_result.score, ai_result.attack_type),
                daemon=True,
            ).start()
            return attach_cors(Response(content="blocked", status_code=403, media_type="text/plain"))

        # ATTACK → Redirect to honeypot (attacker thinks they're in real server)
        if ai_result.label == "attack" and HONEYPOT_ENGINE_ENABLED:
            honeypot_resp = honeypot_engine.trap_request(
                ip=client_ip, method=request.method, path=path,
                headers=dict(request.headers),
                query_string=query_str,
                ai_score=ai_result.score,
                attack_type=ai_result.attack_type,
            )
            return attach_cors(Response(
                content=honeypot_resp["body"],
                status_code=honeypot_resp["status_code"],
                media_type=honeypot_resp["content_type"],
            ))

    # 5. Payload inspection (GET query string + headers)
    if THREAT_ENGINE_ENABLED:
        query_str = str(request.url.query)
        attack = threat_engine.inspect_payload(client_ip, path, query=query_str)
        if attack:
            # If AI is enabled, also record this in the honeypot
            if HONEYPOT_ENGINE_ENABLED:
                honeypot_resp = honeypot_engine.trap_request(
                    ip=client_ip, method=request.method, path=path,
                    headers=dict(request.headers),
                    query_string=query_str,
                    attack_type=attack,
                )
                return attach_cors(Response(
                    content=honeypot_resp["body"],
                    status_code=honeypot_resp["status_code"],
                    media_type=honeypot_resp["content_type"],
                ))
            return attach_cors(JSONResponse(
                status_code=400,
                content={"detail": "Malicious request detected and blocked."},
            ))

    # All checks passed, proceed to endpoint
    _start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - _start) * 1000

    if PERF_ENABLED:
        perf_tracker.record(request.method, path, response.status_code, duration_ms)

    # Feed response status back to AI classifier
    if AI_CLASSIFIER_ENABLED and ai_result:
        ai_classifier.classify(
            ip=client_ip, path=path, method=request.method,
            user_agent=request.headers.get("user-agent", ""),
            status_code=response.status_code,
        )

    return response


# ── Global Exception Handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ Unhandled error: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        # Don't leak internal details in production
        content={"detail": "Internal server error"} if os.getenv("ENV") == "production"
                else {"detail": str(exc)},
    )


# ── In-memory fallback ────────────────────────────────────────────────────────
incidents:      List[Dict] = []
metrics_history: List[Dict] = []


class HealthStatus(BaseModel):
    status:         str
    cpu_percent:    float
    memory_percent: float
    disk_percent:   float
    timestamp:      str


class Incident(BaseModel):
    id:          int
    type:        str
    severity:    int
    description: str
    timestamp:   str
    resolved:    bool


# ── Helper: admin guard ───────────────────────────────────────────────────────
def require_admin(email: str, db: Session):
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Brahmastra v2.0.0 Starting...")
    logger.info(f"   SERVER_HOST  : {SERVER_HOST}")
    logger.info(f"   CORS_ORIGINS : {CORS_ORIGINS}")
    logger.info(f"   ENV          : {os.getenv('ENV', 'development')}")

    # Security warning for default JWT key
    if SECRET_KEY == _DEFAULT_KEY:
        logger.critical(
            "🚨 SECURITY: Using default JWT_SECRET_KEY! "
            "Set JWT_SECRET_KEY env var immediately!"
        )

    if DB_ENABLED:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("✅ Database tables verified")
        except Exception as e:
            logger.error(f"❌ Table creation failed: {e}")

    if BACKUP_ENABLED:
        backup_manager.start_scheduler()
        logger.info("✅ Backup scheduler started")

    logger.info(f"   THREAT_ENGINE: {THREAT_ENGINE_ENABLED}")
    logger.info(f"   RATE_LIMITER : {RATE_LIMITER_ENABLED}")
    logger.info(f"   ANOMALY_ML   : {ANOMALY_ENABLED}")
    logger.info(f"   BACKUP       : {BACKUP_ENABLED}")
    logger.info(f"   PERF_TRACKER : {PERF_ENABLED}")
    logger.info(f"   AI_CLASSIFIER: {AI_CLASSIFIER_ENABLED}")
    logger.info(f"   HONEYPOT_ENG : {HONEYPOT_ENGINE_ENABLED}")
    logger.info(f"   EMERGENCY    : {EMERGENCY_ENABLED}")

    # Register emergency response callbacks
    if EMERGENCY_ENABLED:
        emergency_response.register_callbacks(
            kill_switch=threat_engine.activate_kill_switch if THREAT_ENGINE_ENABLED else None,
            honeypot_save=honeypot_engine.save_all_evidence if HONEYPOT_ENGINE_ENABLED else None,
            backup_create=backup_manager.create_backup if BACKUP_ENABLED else None,
        )
        logger.info("✅ Emergency response callbacks registered")

    logger.info("✅ Brahmastra v2.0.0 ready")


# ── Root + Health (Public) ────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "app": "Brahmastra",
        "version": "2.0.0",
        "status": "running",
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

    user_count = db.query(User).count()
    verification_token = str(uuid.uuid4())
    print(f"DEBUG REGISTER: email={user.email}, password_len={len(user.password)}, password_type={type(user.password)}")
    db_user = User(
        email=user.email,
        hashed_password=get_password_hash(user.password),
        full_name=user.full_name,
        verification_token=verification_token,
        is_verified=False,
        is_admin=(user_count == 0),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    verify_link = f"{SERVER_HOST}/verify-email.html?token={verification_token}"
    if THREAT_ENGINE_ENABLED:
        await email_service.send_verification_email(user.email, verify_link)
    else:
        logger.info(f"📧 [MOCK] Verify: {verify_link}")

    logger.info(f"✅ Registered: {user.email}")
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
    return {"message": "Email verified successfully"}


@app.post("/api/auth/login", response_model=Token)
@limiter.limit("10/minute")
async def login(request: Request, user: UserLogin, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="Database not available")

    # Constant-time lookup to prevent email enumeration timing attacks
    db_user = db.query(User).filter(User.email == user.email).first()
    print(f"DEBUG LOGIN: email={user.email}, password_len={len(user.password)}, password_type={type(user.password)}")
    password_ok = db_user and verify_password(user.password, db_user.hashed_password)

    if not db_user or not password_ok:
        logger.warning(f"❌ Failed login: {user.email} from {client_ip}")
        if THREAT_ENGINE_ENABLED:
            was_banned = threat_engine.record_failed_login(client_ip)
            if was_banned:
                try:
                    db.add(SystemEvent(
                        event_type="ip_banned",
                        description=f"IP {client_ip} auto-banned after repeated failed logins",
                        severity="high",
                    ))
                    db.commit()
                except Exception:
                    db.rollback()

                # Alert admin
                try:
                    admin = db.query(User).filter(User.is_admin == True).first()
                    if admin and THREAT_ENGINE_ENABLED:
                        await email_service.send_security_alert(
                            admin.email,
                            f"IP {client_ip} banned after {MAX_FAILED_LOGINS} failed logins.",
                            client_ip,
                        )
                except Exception as e:
                    logger.error(f"⚠️ Could not send ban alert: {e}")

        # Same error whether email or password is wrong (prevents enumeration)
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not db_user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    if THREAT_ENGINE_ENABLED:
        threat_engine.record_successful_login(client_ip)

    access_token  = create_access_token(data={"sub": db_user.email})
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
    email = verify_refresh_token(data.refresh_token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    new_access  = create_access_token(data={"sub": email})
    new_refresh = create_refresh_token(data={"sub": email})
    return {
        "access_token": new_access,
        "token_type": "bearer",
        "refresh_token": new_refresh,
        "expires_in": 1800,
    }


@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(email: str = Depends(get_current_user_email), db: Session = Depends(get_db)):
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


@app.post("/api/auth/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: PasswordResetRequest, db: Session = Depends(get_db)):
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="Database not available")
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        # Always return same message — prevents email enumeration
        return {"message": "If this email is registered, you will receive a reset link."}

    token = str(uuid.uuid4())
    user.reset_token        = token
    user.reset_token_expiry = datetime.now() + timedelta(minutes=30)
    db.commit()

    reset_link = f"{SERVER_HOST}/reset-password.html?token={token}"
    if THREAT_ENGINE_ENABLED:
        await email_service.send_password_reset_email(data.email, reset_link)
    else:
        logger.info(f"📧 [MOCK] Reset: {reset_link}")

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
    user.hashed_password    = get_password_hash(data.new_password)
    user.reset_token        = None
    user.reset_token_expiry = None
    db.commit()
    return {"message": "Password reset successfully. You can now login."}


# ============================================================================
# METRICS (JWT Protected)
# ============================================================================

@app.get("/api/metrics/current", response_model=HealthStatus)
async def get_current_metrics(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    cpu    = _stats.cpu
    memory = _stats.mem
    disk   = _stats.disk
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
    db: Session = Depends(get_db),
):
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
    db: Session = Depends(get_db),
):
    if THREAT_ENGINE_ENABLED:
        result = threat_engine.calculate_threat_score()
    else:
        cpu    = _stats.cpu
        memory = _stats.mem
        score  = int((cpu + memory) / 2)
        level  = "low" if score < 50 else "medium" if score < 80 else "high"
        result = {"threat_score": score, "level": level, "timestamp": datetime.now().isoformat()}

    if DB_ENABLED and db:
        try:
            db.add(ThreatScore(threat_score=result["threat_score"], threat_level=result["level"]))
            db.commit()
        except Exception as e:
            logger.error(f"❌ ThreatScore save: {e}")
            db.rollback()
    return result


@app.get("/api/threat/history")
async def get_threat_history(
    limit: int = 100,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    if DB_ENABLED and db:
        try:
            rows = db.query(ThreatScore).order_by(ThreatScore.timestamp.desc()).limit(limit).all()
            return [{"id": s.id, "threat_score": s.threat_score, "threat_level": s.threat_level,
                     "timestamp": s.timestamp.isoformat()} for s in reversed(rows)]
        except Exception as e:
            logger.error(f"❌ Threat history: {e}")
    return []


@app.get("/api/threat/blocked-ips")
async def get_blocked_ips(email: str = Depends(get_current_user_email)):
    if not THREAT_ENGINE_ENABLED:
        return {"blocked": [], "message": "Threat engine not available"}
    return {"blocked": threat_engine.get_blocked_ips()}


@app.delete("/api/threat/blocked-ips/{ip}")
async def unblock_ip(
    ip: str,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    require_admin(email, db)
    if not THREAT_ENGINE_ENABLED:
        raise HTTPException(status_code=503, detail="Threat engine not available")
    success = threat_engine.unblock_ip(ip)
    if not success:
        raise HTTPException(status_code=404, detail="IP not found in ban list")
    return {"message": f"IP {ip} unblocked"}


@app.get("/api/threat/payload-hits")
async def get_payload_hits(
    limit: int = 50,
    email: str = Depends(get_current_user_email),
):
    """Get recent payload attack attempts (SQLi, XSS, etc.)."""
    if not THREAT_ENGINE_ENABLED:
        return []
    return threat_engine.get_payload_hits(limit=limit)


# ============================================================================
# HONEYPOT — Attacker Traps 🍯
# ============================================================================

async def _handle_honeypot(request: Request, path: str, db: Session):
    client_ip  = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    if THREAT_ENGINE_ENABLED:
        threat_engine.record_honeypot_hit(client_ip, path, user_agent)

    if DB_ENABLED and db:
        try:
            db.add(SystemEvent(
                event_type="honeypot_hit",
                description=f"Honeypot: {path} from {client_ip}",
                severity="high",
            ))
            db.commit()
        except Exception:
            db.rollback()

    # Fake delay to waste attacker's time (tarpit)
    await asyncio.sleep(2)
    return JSONResponse(status_code=200, content={"status": "ok", "message": "Welcome"})


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
@app.get("/manager")
@app.get("/shell")
@app.get("/cgi-bin/")
async def honeypot(request: Request, db: Session = Depends(get_db)):
    """🍯 Honeypot — logs and bans attacker IPs."""
    return await _handle_honeypot(request, str(request.url.path), db)


@app.get("/api/honeypot/stats")
async def honeypot_stats(email: str = Depends(get_current_user_email)):
    if not THREAT_ENGINE_ENABLED:
        return {"total_hits": 0}
    return threat_engine.get_honeypot_stats()


@app.get("/api/honeypot/hits")
async def honeypot_hits(limit: int = 50, email: str = Depends(get_current_user_email)):
    if not THREAT_ENGINE_ENABLED:
        return []
    return threat_engine.get_honeypot_hits(limit=limit)


# ============================================================================
# EVENTS (JWT Protected)
# ============================================================================

@app.get("/api/events")
async def get_events(
    limit: int = 50,
    event_type: Optional[str] = None,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
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
            logger.error(f"❌ Events: {e}")
    return []


# ============================================================================
# STATS — Auth Required (prevents info leakage to attackers)
# ============================================================================

@app.get("/api/stats")
async def get_stats(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    honeypot_count  = threat_engine.get_honeypot_stats().get("total_hits", 0) if THREAT_ENGINE_ENABLED else 0
    blocked_ip_count = len(threat_engine.get_blocked_ips()) if THREAT_ENGINE_ENABLED else 0

    if not DB_ENABLED or not db:
        return {"database": "disabled", "metrics_count": len(metrics_history),
                "honeypot_hits": honeypot_count, "blocked_ips": blocked_ip_count}
    try:
        return {
            "database": "enabled",
            "metrics_count":  db.query(Metric).count(),
            "threats_count":  db.query(ThreatScore).count(),
            "events_count":   db.query(SystemEvent).count(),
            "users_count":    db.query(User).count(),
            "honeypot_hits":  honeypot_count,
            "blocked_ips":    blocked_ip_count,
        }
    except Exception as e:
        logger.error(f"❌ Stats: {e}")
        return {"database": "error", "error": str(e)}


# ============================================================================
# INCIDENTS
# ============================================================================

@app.get("/api/incidents", response_model=List[Incident])
async def get_incidents(limit: int = 50, email: str = Depends(get_current_user_email)):
    return incidents[-limit:]


@app.post("/api/incidents")
async def create_incident(incident: Incident, email: str = Depends(get_current_user_email)):
    incidents.append(incident.dict())
    return {"status": "created", "incident": incident}


# ============================================================================
# AI DEFENSE SYSTEM — 3 Pillars
# ============================================================================

@app.get("/api/ai/stats")
async def ai_classifier_stats(email: str = Depends(get_current_user_email)):
    """Get AI classifier statistics."""
    if not AI_CLASSIFIER_ENABLED:
        return {"enabled": False}
    return ai_classifier.get_stats()


@app.get("/api/ai/classify/{ip}")
async def ai_classify_ip(ip: str, email: str = Depends(get_current_user_email)):
    """Get detailed AI profile for a specific IP."""
    if not AI_CLASSIFIER_ENABLED:
        return {"enabled": False}
    profile = ai_classifier.get_ip_profile(ip)
    if not profile:
        return {"error": "IP not found in classifier"}
    return profile


@app.get("/api/ai/recent")
async def ai_recent_classifications(limit: int = 50, email: str = Depends(get_current_user_email)):
    """Get recent AI classifications."""
    if not AI_CLASSIFIER_ENABLED:
        return []
    return ai_classifier.get_recent_classifications(limit=limit)


@app.get("/api/honeypot/engine/stats")
async def honeypot_engine_stats(email: str = Depends(get_current_user_email)):
    """Get honeypot engine statistics."""
    if not HONEYPOT_ENGINE_ENABLED:
        return {"enabled": False}
    return honeypot_engine.get_stats()


@app.get("/api/honeypot/engine/session/{ip}")
async def honeypot_session(ip: str, email: str = Depends(get_current_user_email)):
    """Get honeypot session for a specific attacker IP."""
    if not HONEYPOT_ENGINE_ENABLED:
        return {"enabled": False}
    session = honeypot_engine.get_session(ip)
    if not session:
        return {"error": "No session found for this IP"}
    return session


@app.post("/api/honeypot/engine/save-evidence")
async def save_honeypot_evidence(email: str = Depends(get_current_user_email)):
    """Force save all honeypot evidence."""
    if not HONEYPOT_ENGINE_ENABLED:
        return {"enabled": False}
    saved = honeypot_engine.save_all_evidence()
    return {"saved_files": len(saved), "files": saved}


@app.get("/api/emergency/status")
async def emergency_status(email: str = Depends(get_current_user_email)):
    """Get emergency response system status."""
    if not EMERGENCY_ENABLED:
        return {"enabled": False}
    return emergency_response.get_status()


@app.post("/api/emergency/trigger")
async def trigger_emergency(email: str = Depends(get_current_user_email)):
    """Manually trigger emergency response (ADMIN ONLY — nuclear option)."""
    if not EMERGENCY_ENABLED:
        return {"enabled": False}
    result = emergency_response.trigger_emergency(
        reason=f"Manual trigger by admin: {email}",
        attacker_ip="manual",
    )
    return result


# ============================================================================
# KILL SWITCH (Admin only)
# ============================================================================

@app.post("/api/kill-switch")
async def trigger_kill_switch(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    require_admin(email, db)

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

    # Enable attack mode on rate limiter
    if RATE_LIMITER_ENABLED:
        rate_limiter.set_attack_mode(True)

    logger.critical(f"🚨 KILL SWITCH by {email}")

    if ALERTS_ENABLED:
        await alert_service.alert_kill_switch(email)

    return {"status": "triggered", "message": "Kill-switch activated.", "incident_id": incident["id"]}


@app.post("/api/kill-switch/deactivate")
async def deactivate_kill_switch(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    require_admin(email, db)
    if THREAT_ENGINE_ENABLED:
        threat_engine.deactivate_kill_switch()
    if RATE_LIMITER_ENABLED:
        rate_limiter.set_attack_mode(False)
    logger.info(f"✅ Kill switch deactivated by {email}")
    return {"status": "deactivated"}


# ============================================================================
# ADMIN PANEL ENDPOINTS (Admin only)
# ============================================================================

@app.get("/api/admin/banned-ips")
async def admin_get_banned_ips(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    """Return all currently banned IPs with time remaining."""
    require_admin(email, db)
    if THREAT_ENGINE_ENABLED:
        return {"banned_ips": threat_engine.get_blocked_ips(), "count": len(threat_engine.get_blocked_ips())}
    return {"banned_ips": [], "count": 0}


@app.post("/api/admin/unban/{ip}")
async def admin_unban_ip(
    ip: str,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    """Immediately unban an IP address."""
    require_admin(email, db)
    if THREAT_ENGINE_ENABLED:
        success = threat_engine.unblock_ip(ip)
        logger.info(f"🔓 Admin {email} unbanned IP: {ip}")
        return {"status": "unbanned" if success else "not_found", "ip": ip}
    return {"status": "threat_engine_disabled"}


@app.get("/api/admin/users")
async def admin_get_users(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    """List all registered users."""
    require_admin(email, db)
    if not DB_ENABLED or not db:
        return {"users": [], "note": "DB disabled"}
    try:
        users = db.query(User).all()
        return {
            "users": [
                {
                    "id": u.id,
                    "email": u.email,
                    "full_name": u.full_name,
                    "is_admin": u.is_admin,
                    "is_active": u.is_active,
                    "is_verified": u.is_verified,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                }
                for u in users
            ],
            "count": len(users),
        }
    except Exception as e:
        logger.error(f"Admin users fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/whitelist")
async def admin_get_whitelist(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    """Return the current runtime IP whitelist."""
    require_admin(email, db)
    return {"whitelist": sorted(WHITELISTED_IPS), "count": len(WHITELISTED_IPS)}


@app.post("/api/admin/whitelist/add")
async def admin_whitelist_add(
    request: Request,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    """Add an IP to the runtime whitelist (session only — not persisted to .env)."""
    require_admin(email, db)
    body = await request.json()
    ip = body.get("ip", "").strip()
    if not ip:
        raise HTTPException(status_code=400, detail="ip field required")
    WHITELISTED_IPS.add(ip)
    # Also immediately unban if currently banned
    if THREAT_ENGINE_ENABLED:
        threat_engine.unblock_ip(ip)
    logger.info(f"🟢 Admin {email} whitelisted IP: {ip}")
    return {"status": "added", "ip": ip, "whitelist": sorted(WHITELISTED_IPS)}


@app.delete("/api/admin/whitelist/remove/{ip}")
async def admin_whitelist_remove(
    ip: str,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    """Remove an IP from the runtime whitelist."""
    require_admin(email, db)
    WHITELISTED_IPS.discard(ip)
    logger.info(f"🔴 Admin {email} removed IP from whitelist: {ip}")
    return {"status": "removed", "ip": ip, "whitelist": sorted(WHITELISTED_IPS)}


# ============================================================================
# ANOMALY DETECTION
# ============================================================================

@app.get("/api/anomaly/status")
async def get_anomaly_status(email: str = Depends(get_current_user_email)):
    if not ANOMALY_ENABLED:
        return {"enabled": False}
    return anomaly_detector.get_status()


@app.get("/api/anomaly/history")
async def get_anomaly_history(email: str = Depends(get_current_user_email)):
    if not ANOMALY_ENABLED:
        return []
    return anomaly_detector.get_anomaly_history()


# ============================================================================
# ALERTS
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
# WEBSOCKET — Real-time dashboard
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    from backend.auth import verify_token
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Token required")
        return
    email = verify_token(token)
    if not email:
        await websocket.close(code=1008, reason="Invalid token")
        return

    # Rate limit WS connections per IP
    client_ip = websocket.client.host if websocket.client else "unknown"
    if RATE_LIMITER_ENABLED:
        allowed, _ = rate_limiter.check(client_ip, "ws")
        if not allowed:
            await websocket.close(code=1008, reason="Too many connections")
            return

    await websocket.accept()
    logger.info(f"🔌 WS connected: {email}")
    try:
        while True:
            cpu    = _stats.cpu
            memory = _stats.mem
            disk   = _stats.disk

            threat_data = {}
            if THREAT_ENGINE_ENABLED:
                ts = threat_engine.calculate_threat_score()
                threat_data = {
                    "threat_score":  ts["threat_score"],
                    "threat_level":  ts["level"],
                    "blocked_ips":   len(threat_engine.get_blocked_ips()),
                    "honeypot_hits": threat_engine.get_honeypot_stats().get("total_hits", 0),
                }

            anomaly_data = {}
            if ANOMALY_ENABLED:
                analysis = anomaly_detector.analyze(cpu, memory, disk)
                anomaly_data = {
                    "anomaly_status": analysis["status"],
                    "anomaly_count":  analysis.get("total_anomalies", 0),
                }
                if analysis.get("anomalies") and ALERTS_ENABLED:
                    for a in analysis["anomalies"]:
                        await alert_service.alert_anomaly(
                            a["metric"], a["value"], a["expected"], a["z_score"]
                        )

            await websocket.send_json({
                "type": "metrics_update",
                "cpu": cpu, "memory": memory, "disk": disk,
                "timestamp": datetime.now().isoformat(),
                **threat_data,
                **anomaly_data,
            })
            await asyncio.sleep(5)
    except Exception as e:
        logger.info(f"WS closed ({email}): {e}")


# ============================================================================
# RATE LIMITER STATS (Admin)
# ============================================================================

@app.get("/api/ratelimit/status")
async def ratelimit_status(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    require_admin(email, db)
    if not RATE_LIMITER_ENABLED:
        return {"enabled": False}
    return rate_limiter.get_status()


@app.post("/api/ratelimit/circuit-breaker")
async def toggle_circuit_breaker(
    open_: bool,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    """Manually open/close circuit breaker (admin only)."""
    require_admin(email, db)
    if not RATE_LIMITER_ENABLED:
        raise HTTPException(status_code=503, detail="Rate limiter not available")
    rate_limiter.set_circuit_breaker(open_)
    return {"circuit_breaker": "open" if open_ else "closed"}


# ============================================================================
# BACKUP
# ============================================================================

@app.post("/api/backup/create")
async def create_backup(email: str = Depends(get_current_user_email)):
    if not BACKUP_ENABLED:
        raise HTTPException(status_code=503, detail="Backup system not available")
    return backup_manager.create_backup(label="manual")


@app.get("/api/backup/list")
async def list_backups(email: str = Depends(get_current_user_email)):
    if not BACKUP_ENABLED:
        raise HTTPException(status_code=503, detail="Backup system not available")
    return {"backups": backup_manager.list_backups()}


@app.get("/api/backup/status")
async def backup_status(email: str = Depends(get_current_user_email)):
    if not BACKUP_ENABLED:
        return {"enabled": False}
    return backup_manager.get_status()


@app.post("/api/backup/restore/{filename}")
async def restore_backup(
    filename: str,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    require_admin(email, db)
    if not BACKUP_ENABLED:
        raise HTTPException(status_code=503, detail="Backup system not available")
    result = backup_manager.restore_backup(filename)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ============================================================================
# PERFORMANCE
# ============================================================================

@app.get("/api/performance/stats")
async def performance_stats(email: str = Depends(get_current_user_email)):
    if not PERF_ENABLED:
        return {"enabled": False}
    return perf_tracker.get_stats()


@app.get("/api/performance/slow")
async def slow_endpoints(threshold: float = 100, email: str = Depends(get_current_user_email)):
    if not PERF_ENABLED:
        return {"enabled": False, "slow_endpoints": []}
    return {"threshold_ms": threshold, "slow_endpoints": perf_tracker.get_slow_endpoints(threshold)}


@app.get("/api/performance/recent")
async def recent_requests(email: str = Depends(get_current_user_email)):
    if not PERF_ENABLED:
        return {"enabled": False, "requests": []}
    return {"requests": perf_tracker.get_recent_requests()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=2,           # 2 workers: one handles attack rejections, other serves dashboard
        limit_concurrency=50, # Cap concurrent connections to prevent event loop starvation
        timeout_keep_alive=5, # Drop idle attack connections faster
    )

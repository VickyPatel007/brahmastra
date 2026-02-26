from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str
    full_name: Optional[str] = None

class UserLogin(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    full_name: Optional[str] = None
    is_active: bool
    is_verified: bool
    is_admin: bool = False
    created_at: datetime

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None
    expires_in: int = 1800  # 30 minutes in seconds

class RefreshToken(BaseModel):
    refresh_token: str

class TokenData(BaseModel):
    email: Optional[str] = None

class MetricResponse(BaseModel):
    id: int
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    status: str
    timestamp: datetime

    class Config:
        orm_mode = True

class ThreatScoreResponse(BaseModel):
    id: int
    threat_score: int
    threat_level: str
    timestamp: datetime

    class Config:
        orm_mode = True

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from fleetpulse.auth.roles import MembershipRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class LogoutRequest(RefreshRequest):
    pass


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime


class OrganizationSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    default_currency: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    membership_id: uuid.UUID
    role: MembershipRole
    organization: OrganizationSummary


class MemberResponse(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    display_name: str
    role: MembershipRole
    is_active: bool


class MemberListResponse(BaseModel):
    items: list[MemberResponse]

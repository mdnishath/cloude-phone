from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=512)


class TokenPair(BaseModel):
    access: str
    refresh: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh: str


class RedeemInviteRequest(BaseModel):
    token: str = Field(min_length=10, max_length=128)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

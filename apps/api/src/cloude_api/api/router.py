"""Mount all v1 routers under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from cloude_api.api import auth, device_profiles, devices, me, proxies

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(me.router)
api_v1.include_router(device_profiles.router)
api_v1.include_router(proxies.router)
api_v1.include_router(devices.router)

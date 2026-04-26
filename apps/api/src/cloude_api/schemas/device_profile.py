from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class DeviceProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    android_version: str
    screen_width: int
    screen_height: int
    screen_dpi: int
    ram_mb: int
    cpu_cores: int
    manufacturer: str
    model: str
    is_public: bool

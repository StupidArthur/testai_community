"""Pydantic 响应模型（SSE 除外）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class JobView(BaseModel):
    job_id: str
    name: str
    username: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    created_at: str
    updated_at: str
    current_phase: str
    current_step: int
    total_steps: int
    message: str
    queue_ahead: int
    queue_total: int
    error: str | None


class UploadResponse(BaseModel):
    job_id: str
    status: str
    queue_ahead: int
    queue_total: int
    total_steps: int
    current_step: int

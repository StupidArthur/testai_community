"""SSE 事件生成器 + 事件类型定义。"""

from __future__ import annotations

import asyncio
import json
from typing import Literal, TypedDict

from fastapi import Request

from . import jobs as J


class ProgressEvent(TypedDict):
    type: Literal["progress"]
    phase: str
    step: int
    total_steps: int
    message: str


class QueuedEvent(TypedDict):
    type: Literal["queued"]
    ahead: int
    total: int


class DoneEvent(TypedDict):
    type: Literal["done"]
    status: str
    error: str | None


SseEvent = ProgressEvent | QueuedEvent | DoneEvent


async def event_gen(job: J.Job, request: Request):
    if job.last_event:
        yield f"data: {json.dumps(job.last_event, ensure_ascii=False)}\n\n"

    while True:
        if await request.is_disconnected():
            return
        if job.status == J.JobStatus.QUEUED:
            ahead, total = J.get_queue_position(job.id)
            ev: SseEvent = {"type": "queued", "ahead": ahead, "total": total}
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            try:
                await asyncio.wait_for(job.event_queue.get(), timeout=3.0)
                if job.last_event:
                    yield f"data: {json.dumps(job.last_event, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                pass
        elif job.status == J.JobStatus.RUNNING:
            try:
                ev = await asyncio.wait_for(job.event_queue.get(), timeout=15.0)
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
        else:
            yield f"data: {json.dumps({'type': 'done', 'status': job.status.value, 'error': job.error}, ensure_ascii=False)}\n\n"
            return

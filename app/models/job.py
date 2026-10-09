"""In-memory job model (no database in v1)."""

from __future__ import annotations

import asyncio
import itertools
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

_SEQ = itertools.count(1)


class JobStage(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {JobStage.DONE, JobStage.CANCELLED, JobStage.FAILED}

    @property
    def is_live(self) -> bool:
        """Stages whose progress message is refreshed periodically."""
        return self in {
            JobStage.QUEUED,
            JobStage.DOWNLOADING,
            JobStage.UPLOADING,
            JobStage.PROCESSING,
        }


def new_job_id() -> str:
    return secrets.token_hex(4)


@dataclass
class Job:
    owner_user_id: int
    chat_id: int
    file_id: int
    file_name: str
    file_size: int
    mime_type: str = "video/mp4"
    duration: int = 0
    width: int = 0
    height: int = 0
    is_video: bool = True
    source_message_id: int = 0

    job_id: str = field(default_factory=new_job_id)
    seq: int = field(default_factory=lambda: next(_SEQ))
    stage: JobStage = JobStage.QUEUED
    message_id: int = 0  # the single progress message of this job
    last_text: str = ""

    temp_path: Path | None = None

    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    processing_started_at: float | None = None
    finished_at: float | None = None

    downloaded_bytes: int = 0
    download_speed: float = 0.0
    uploaded_bytes: int = 0
    upload_speed: float = 0.0
    upload_started_at: float | None = None

    abyss_slug: str | None = None
    abyss_status: str | None = None
    player_url: str | None = None
    iframe_url: str | None = None
    page_url: str | None = None
    direct_url: str | None = None
    skipped_wait: bool = False

    error: str | None = None
    cancelled_stage: str = ""

    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    skip_event: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: asyncio.Task | None = None

    @property
    def total_bytes(self) -> int:
        return self.file_size or 0

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0.0, end - self.started_at)

    @property
    def processing_elapsed(self) -> float:
        if self.processing_started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0.0, end - self.processing_started_at)

    @property
    def watch_url(self) -> str | None:
        return self.player_url or self.iframe_url or self.page_url

    def request_cancel(self) -> None:
        if self.cancel_event.is_set():
            return
        self.cancel_event.set()
        if self.task is not None and not self.task.done():
            self.task.cancel()

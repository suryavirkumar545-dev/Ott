"""Telegram download through TDLib.

Why the old version failed with ``400``: TDLib's ``downloadFile`` requires
``priority`` in the range 1..32, but the generated Pytdbot signature defaults it
to ``0``.  We now always pass ``priority=32``.

Progress is read from TDLib (``updateFile`` + ``getFile`` polling), the speed is
a smoothed average, and a stalled download is detected and restarted.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import pytdbot

from app.models.job import Job

logger = logging.getLogger(__name__)
T = pytdbot.types

POLL_SECONDS = 1.0
STALL_SECONDS = 180
MAX_RESTARTS = 3


class DownloadError(RuntimeError):
    """User-safe download failure."""


def _err_text(error) -> str:
    return f"{getattr(error, 'code', '?')} {getattr(error, 'message', '')}".strip()


class DownloadService:
    def __init__(self) -> None:
        self._by_file_id: dict[int, Job] = {}

    # called from the updateFile handler -----------------------------------
    def on_file_update(self, file) -> None:
        job = self._by_file_id.get(getattr(file, "id", None))
        local = getattr(file, "local", None)
        if job is not None and local is not None:
            job.downloaded_bytes = max(job.downloaded_bytes, local.downloaded_size or 0)

    # ----------------------------------------------------------------------
    @staticmethod
    async def _start(client, job: Job) -> None:
        result = await client.downloadFile(
            file_id=job.file_id, priority=32, offset=0, limit=0, synchronous=False
        )
        if isinstance(result, T.Error):
            logger.error("Job %s: downloadFile error %s", job.job_id, _err_text(result))
            raise DownloadError(f"Telegram refused the download ({_err_text(result)})")

    @staticmethod
    async def _cancel_remote(client, job: Job) -> None:
        try:
            await client.cancelDownloadFile(file_id=job.file_id, only_if_pending=False)
        except Exception as exc:  # noqa: BLE001
            logger.debug("cancelDownloadFile failed: %s", exc)

    async def download(self, client, job: Job) -> Path:
        self._by_file_id[job.file_id] = job
        restarts = 0
        errors = 0
        last_bytes = -1
        last_progress = time.monotonic()
        last_sample = (time.monotonic(), 0)
        job.download_speed = 0.0
        try:
            await self._start(client, job)
            while True:
                if job.cancel_event.is_set():
                    raise asyncio.CancelledError("download cancelled")

                file = await client.getFile(file_id=job.file_id)
                if isinstance(file, T.Error):
                    errors += 1
                    if errors >= 5:
                        raise DownloadError(f"Telegram getFile failed ({_err_text(file)})")
                    await asyncio.sleep(POLL_SECONDS)
                    continue
                errors = 0

                local = file.local
                size = int(file.size or file.expected_size or 0)
                if size:
                    job.file_size = size
                done = int(local.downloaded_size or 0) if local else 0
                job.downloaded_bytes = max(done, 0)

                now = time.monotonic()
                dt = now - last_sample[0]
                if dt >= 1.0:
                    inst = max(0.0, (done - last_sample[1]) / dt)
                    job.download_speed = inst if job.download_speed == 0 else (
                        0.6 * job.download_speed + 0.4 * inst
                    )
                    last_sample = (now, done)

                if local is not None and local.is_downloading_completed and local.path:
                    path = Path(local.path)
                    if not path.exists():
                        raise DownloadError("Downloaded file is missing on disk")
                    real = path.stat().st_size
                    if job.file_size and real < job.file_size:
                        raise DownloadError("Downloaded file is incomplete")
                    job.temp_path = path
                    job.file_size = job.file_size or real
                    job.downloaded_bytes = real
                    logger.info("Job %s: Telegram download completed (%d bytes)", job.job_id, real)
                    return path

                if done != last_bytes:
                    last_bytes = done
                    last_progress = now

                active = bool(local and local.is_downloading_active)
                stalled = now - last_progress > STALL_SECONDS
                if (not active and now - last_progress > 8) or stalled:
                    if restarts >= MAX_RESTARTS:
                        raise DownloadError("Telegram download stalled")
                    restarts += 1
                    logger.warning("Job %s: download inactive, restart %d", job.job_id, restarts)
                    await self._start(client, job)
                    last_progress = time.monotonic()
                await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            await self._cancel_remote(client, job)
            raise
        finally:
            self._by_file_id.pop(job.file_id, None)

    @staticmethod
    async def remove_from_tdlib(client, job: Job) -> None:
        """Drop TDLib's cached copy so nothing stays on disk."""
        try:
            await client.deleteFile(file_id=job.file_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("deleteFile failed: %s", exc)


def disk_has_room(free_bytes: int, size: int) -> bool:
    return free_bytes == 0 or free_bytes >= int(size * 1.05) + 64 * 1024 * 1024


__all__ = ["DownloadService", "DownloadError", "disk_has_room"]

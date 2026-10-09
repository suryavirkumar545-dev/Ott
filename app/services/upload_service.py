"""Per-job pipeline.

    worker slot:   check limits -> TDLib download -> Abyss upload -> free disk
    watcher task:  poll Abyss until ready -> final message with the URLs

The queue worker is released as soon as the *upload* finishes; Abyss'
server-side processing is awaited by a separate lightweight watcher so the next
file starts downloading immediately and a long batch never stalls.
"""

from __future__ import annotations

import asyncio
import errno
import logging
import time

from app.config import Config
from app.models.job import Job, JobStage
from app.services.abyss_service import AbyssError, AbyssService
from app.services.cleanup_service import CleanupService
from app.services.download_service import DownloadError, DownloadService, disk_has_room
from app.services.progress_service import ProgressService

logger = logging.getLogger(__name__)


def _url(value) -> str | None:
    return value if isinstance(value, str) and value.startswith(("http://", "https://")) else None


def apply_links(job: Job, data: dict) -> None:
    """Copy only the URLs Abyss really returned (nothing is invented)."""
    iframe = _url(data.get("urlIframe"))
    page = _url(data.get("url"))
    direct = _url(data.get("urlDirect")) or _url(data.get("directUrl"))
    if iframe:
        job.iframe_url = iframe
    if page:
        job.page_url = page
    if direct:
        job.direct_url = direct
    job.player_url = job.iframe_url or job.page_url


def user_message(exc: BaseException) -> str:
    if isinstance(exc, (DownloadError, AbyssError)):
        return str(exc)
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return "The server disk is full."
    if isinstance(exc, (ConnectionError, asyncio.TimeoutError)):
        return "Network problem. Please try again."
    return f"Unexpected error ({type(exc).__name__})."


class UploadService:
    def __init__(self, client, config: Config, abyss: AbyssService, downloads: DownloadService,
                 cleanup: CleanupService, progress: ProgressService) -> None:
        self._client = client
        self._config = config
        self._abyss = abyss
        self._downloads = downloads
        self._cleanup = cleanup
        self._progress = progress
        self._watchers: set[asyncio.Task] = set()
        self._watch_slots = asyncio.Semaphore(max(1, config.max_processing_watchers))

    # ------------------------------------------------------------------ #
    async def run(self, job: Job) -> None:
        """Called by a queue worker. Returns when the worker slot is free."""
        task = asyncio.create_task(self._transfer(job), name=f"transfer-{job.job_id}")
        job.task = task
        try:
            uploaded = await task
        except asyncio.CancelledError:  # worker is shutting down
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        if uploaded:
            watcher = asyncio.create_task(self._watch(job), name=f"watch-{job.job_id}")
            job.task = watcher
            self._watchers.add(watcher)
            watcher.add_done_callback(self._watchers.discard)

    async def shutdown(self) -> None:
        for watcher in list(self._watchers):
            watcher.cancel()
        await asyncio.gather(*self._watchers, return_exceptions=True)

    # ------------------------------------------------------------------ #
    async def _transfer(self, job: Job) -> bool:
        """Download + upload. Returns True when the file is on Abyss."""
        job.started_at = time.time()
        try:
            await self._abyss.check_capacity(job.file_size)
            if job.file_size and not disk_has_room(self._cleanup.free_bytes(), job.file_size):
                raise DownloadError("Not enough free disk space on the server.")

            # ---- 1. Telegram -> disk ------------------------------------
            job.stage = JobStage.DOWNLOADING
            job.downloaded_bytes = 0
            await self._progress.push(job, final=True)
            logger.info("Job %s: Telegram download started", job.job_id)
            path = await self._downloads.download(self._client, job)

            # ---- 2. disk -> Abyss ---------------------------------------
            job.stage = JobStage.UPLOADING
            job.uploaded_bytes = 0
            job.upload_speed = 0.0
            job.upload_started_at = time.time()
            await self._progress.push(job, final=True)
            logger.info("Job %s: Abyss upload started", job.job_id)

            def on_progress(done: int, total: int, speed: float) -> None:
                job.uploaded_bytes = done
                job.upload_speed = speed

            result = await self._abyss.upload(path, job.file_name, job.mime_type, on_progress)
            job.abyss_slug = result.get("slug")
            apply_links(job, result)
            job.uploaded_bytes = job.file_size
            logger.info("Job %s: Abyss upload completed", job.job_id)

            job.stage = JobStage.PROCESSING
            job.processing_started_at = time.time()
            job.abyss_status = "processing"
            await self._progress.push(job, final=True)
            return True

        except asyncio.CancelledError:
            job.cancelled_stage = "download" if job.stage is JobStage.DOWNLOADING else "upload"
            logger.info("Job %s cancelled during %s", job.job_id, job.cancelled_stage)
            await self._progress.finish(job, JobStage.CANCELLED)
            return False
        except Exception as exc:  # noqa: BLE001
            if not isinstance(exc, (DownloadError, AbyssError)):
                logger.exception("Job %s unexpected error", job.job_id)
            await self._fail(job, user_message(exc), exc)
            return False
        finally:
            self._cleanup.delete_path(job.temp_path)
            job.temp_path = None
            try:
                await asyncio.shield(self._downloads.remove_from_tdlib(self._client, job))
            except asyncio.CancelledError:
                pass
            logger.info("Job %s: temporary files cleaned", job.job_id)

    # ------------------------------------------------------------------ #
    async def _watch(self, job: Job) -> None:
        def on_tick(info: dict) -> None:
            job.abyss_status = str(info.get("status") or job.abyss_status or "processing")
            apply_links(job, info)

        try:
            async with self._watch_slots:
                info, skipped = await self._abyss.wait_until_ready(
                    job.abyss_slug, job.cancel_event, job.skip_event, on_tick
                )
            if info:
                apply_links(job, info)
                job.abyss_status = str(info.get("status") or job.abyss_status)
            job.skipped_wait = skipped
            logger.info("Job %s: finished (%s)", job.job_id, "skipped wait" if skipped else "ready")
            await self._progress.finish(job, JobStage.DONE)
        except asyncio.CancelledError:
            if job.cancel_event.is_set():
                job.cancelled_stage = "abyss wait"
                await self._progress.finish(job, JobStage.CANCELLED)
            else:
                raise  # application shutdown
        except Exception as exc:  # noqa: BLE001
            if not isinstance(exc, AbyssError):
                logger.exception("Job %s watcher error", job.job_id)
            await self._fail(job, user_message(exc), exc)

    async def _fail(self, job: Job, message: str, exc: BaseException | None = None) -> None:
        job.error = message
        logger.error("Job %s failed: %s (%s)", job.job_id, message,
                     type(exc).__name__ if exc else "-")
        await self._progress.finish(job, JobStage.FAILED)

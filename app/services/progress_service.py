"""Job registry + throttled progress messages.

* ONE Telegram message per job (sent once, then edited).
* A single background loop refreshes live jobs every ``progress_update_interval``
  seconds - TDLib file updates never trigger edits directly.
* Immediate edits on stage changes (start, done, cancelled, failed).
* Every edit renders the text *inside* a per-job lock, so a slow, stale edit can
  never overwrite a newer one (e.g. "processing" over "complete").
* Telegram flood waits (429) pause all edits until they expire.
* Final messages are retried and, if editing is impossible, re-sent - the URL
  is never lost.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

from app.config import Config
from app.models.job import Job, JobStage
from app.services import telegram_service as tg
from app.ui import progress as progress_ui

logger = logging.getLogger(__name__)

KEEP_FINISHED_SECONDS = 3600


class ProgressService:
    def __init__(self, client, config: Config, allow_delete: bool = False) -> None:
        self._client = client
        self._config = config
        self._allow_delete = allow_delete
        self._jobs: dict[str, Job] = {}
        self._task: asyncio.Task | None = None
        self._blocked_until = 0.0

    # registry ----------------------------------------------------------
    def register(self, job: Job) -> None:
        self._jobs[job.job_id] = job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def all_jobs(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.seq)

    def queued_jobs(self) -> list[Job]:
        return [j for j in self.all_jobs() if j.stage is JobStage.QUEUED]

    def active_jobs(self) -> list[Job]:
        return [j for j in self.all_jobs() if j.stage.is_live]

    # lifecycle ---------------------------------------------------------
    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="progress-loop")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._config.progress_update_interval)
            try:
                for job in list(self._jobs.values()):
                    if job.stage.is_live:
                        await self.push(job)
                self._prune()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("progress loop error")

    def _prune(self) -> None:
        now = time.time()
        for job_id, job in list(self._jobs.items()):
            if job.stage.is_terminal and job.finished_at and now - job.finished_at > KEEP_FINISHED_SECONDS:
                self._jobs.pop(job_id, None)

    # rendering ---------------------------------------------------------
    def _render(self, job: Job):
        queued = self.queued_jobs()
        position = queued.index(job) + 1 if job in queued else 1
        running = [j for j in self.all_jobs() if j.stage in (JobStage.DOWNLOADING, JobStage.UPLOADING)]
        return progress_ui.render(
            job,
            allow_delete=self._allow_delete,
            position=position,
            total=max(len(queued), 1),
            active_name=running[0].file_name if running else None,
        )

    async def push(self, job: Job, *, final: bool = False) -> bool:
        """Refresh the job's message. ``final`` = must be delivered."""
        async with job.lock:
            text, markup = self._render(job)
            if text == job.last_text and job.message_id and not final:
                return True
            return await self._deliver(job, text, markup, final)

    async def _deliver(self, job: Job, text: str, markup, final: bool) -> bool:
        attempts = 4 if final else 1
        for _ in range(attempts):
            wait = self._blocked_until - time.time()
            if wait > 0:
                if not final:
                    return False
                await asyncio.sleep(min(wait, 60))

            if not job.message_id:
                result = await tg.send_text(self._client, job.chat_id, text, markup)
            else:
                result = await tg.edit_text(self._client, job.chat_id, job.message_id, text, markup)

            if not tg.is_error(result):
                if not job.message_id:
                    job.message_id = result.id
                job.last_text = text
                return True

            code = getattr(result, "code", 0)
            message = str(getattr(result, "message", "") or "")
            if code == 429:
                seconds = re.search(r"(\d+)", message)
                self._blocked_until = time.time() + (int(seconds.group(1)) if seconds else 5) + 1
                logger.warning("Telegram flood wait %ss", int(self._blocked_until - time.time()))
                continue
            if "not modified" in message.lower():
                job.last_text = text
                return True
            if job.message_id and ("not found" in message.lower() or "can't be edited" in message.lower()):
                job.message_id = 0  # resend as a new message
                continue
            logger.debug("Message update failed for %s: %s %s", job.job_id, code, message)
            if not final:
                return False
        return False

    async def finish(self, job: Job, stage: JobStage) -> None:
        job.stage = stage
        job.finished_at = time.time()
        await self.push(job, final=True)

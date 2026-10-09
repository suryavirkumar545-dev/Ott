"""Asynchronous job queue with a configurable number of workers."""

from __future__ import annotations

import asyncio
import logging

from app.models.job import Job, JobStage

logger = logging.getLogger(__name__)


class QueueService:
    def __init__(self, upload_service, progress, workers: int = 1) -> None:
        self._upload = upload_service
        self._progress = progress
        self._workers = max(1, workers)
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        for index in range(self._workers):
            self._tasks.append(asyncio.create_task(self._worker(index), name=f"worker-{index}"))
        logger.info("Queue started with %d worker(s)", self._workers)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self._upload.shutdown()

    def enqueue(self, job: Job) -> None:
        job.stage = JobStage.QUEUED
        self._queue.put_nowait(job)
        logger.info("Job %s queued (%s)", job.job_id, job.file_name)

    @property
    def size(self) -> int:
        return self._queue.qsize()

    async def _worker(self, index: int) -> None:
        while True:
            job = await self._queue.get()
            try:
                if job.stage is not JobStage.QUEUED or job.cancel_event.is_set():
                    continue  # cancelled while waiting
                logger.info("Worker %d took job %s", index, job.job_id)
                await self._upload.run(job)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a worker must never die
                logger.exception("Worker %d crashed on job %s", index, job.job_id)
            finally:
                self._queue.task_done()

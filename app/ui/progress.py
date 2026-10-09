"""Map a job's current stage to its message text and keyboard."""

from __future__ import annotations

from app.models.job import Job, JobStage
from app.ui import keyboards, messages


def render(job: Job, *, allow_delete: bool = False, position: int = 1, total: int = 1,
           active_name: str | None = None):
    stage = job.stage
    if stage is JobStage.QUEUED:
        return messages.queued(job, position, total, active_name), keyboards.cancel_queued(job)
    if stage is JobStage.DOWNLOADING:
        return messages.downloading(job), keyboards.cancel_download(job)
    if stage is JobStage.UPLOADING:
        return messages.uploading(job), keyboards.cancel_upload(job)
    if stage is JobStage.PROCESSING:
        return messages.processing(job), keyboards.skip_wait(job)
    if stage is JobStage.DONE:
        return messages.completed(job), keyboards.result(job, allow_delete=allow_delete)
    if stage is JobStage.CANCELLED:
        return messages.cancelled(job), None
    return messages.failed(job), None

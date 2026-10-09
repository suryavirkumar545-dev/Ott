"""Incoming video / video-document -> job -> queue (no confirmation step)."""

from __future__ import annotations

import logging

from app.config import config
from app.models.job import Job
from app.services.telegram_service import UnsupportedMedia, extract_media, send_text
from app.ui import messages

logger = logging.getLogger(__name__)


async def handle(app, message, user_id: int) -> bool:
    try:
        media = extract_media(message)
    except UnsupportedMedia:
        await send_text(app.client, message.chat_id, messages.unsupported())
        return True
    if media is None:
        return False

    limit = min(config.max_file_size_bytes, app.effective_limit_bytes)
    if media["file_size"] and media["file_size"] > limit:
        await send_text(
            app.client, message.chat_id,
            messages.too_large(media["file_name"], media["file_size"], limit // (1024 * 1024)),
        )
        return True

    job = Job(
        owner_user_id=user_id,
        chat_id=message.chat_id,
        file_id=media["file_id"],
        file_name=media["file_name"],
        file_size=media["file_size"],
        mime_type=media["mime_type"],
        duration=media["duration"],
        width=media["width"],
        height=media["height"],
        is_video=media["is_video"],
        source_message_id=message.id,
    )
    app.progress.register(job)
    app.queue.enqueue(job)  # synchronous: keeps the order of an album
    await app.progress.push(job, final=True)
    logger.info("Job %s accepted (%s, %d bytes)", job.job_id, job.file_name, job.file_size)
    return True

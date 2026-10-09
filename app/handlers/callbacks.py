"""Inline-button callbacks. Every action verifies the job owner."""

from __future__ import annotations

import logging

import pytdbot

from app.config import config
from app.models.job import JobStage
from app.services.abyss_service import AbyssError
from app.utils.callbacks import CallbackAction, decode

logger = logging.getLogger(__name__)


async def _answer(client, update, text: str = "", alert: bool = False) -> None:
    try:
        await client.answerCallbackQuery(callback_query_id=update.id, text=text, show_alert=alert)
    except Exception as exc:  # noqa: BLE001
        logger.debug("answerCallbackQuery failed: %s", exc)


def register(app) -> None:
    @app.client.on_updateNewCallbackQuery()
    async def on_callback(client, update):
        payload = update.payload
        raw = payload.data if isinstance(payload, pytdbot.types.CallbackQueryPayloadData) else None
        callback = decode(raw)
        if callback is None:
            return await _answer(client, update, "Unsupported action", True)
        if not config.is_allowed(update.sender_user_id):
            return await _answer(client, update, "Private bot", True)

        job = app.progress.get(callback.job_id)
        if job is None:
            return await _answer(client, update, "This job has expired", True)
        if job.owner_user_id != update.sender_user_id:  # ownership check
            return await _answer(client, update, "This is not your upload", True)

        action = callback.action

        if action is CallbackAction.CANCEL_QUEUED:
            if job.stage is not JobStage.QUEUED:
                return await _answer(client, update, "Already started - use the cancel button below")
            await _answer(client, update, "Cancelled")
            job.cancel_event.set()
            job.cancelled_stage = "queue"
            await app.progress.finish(job, JobStage.CANCELLED)

        elif action in (CallbackAction.CANCEL_DOWNLOAD, CallbackAction.CANCEL_UPLOAD):
            if job.stage not in (JobStage.DOWNLOADING, JobStage.UPLOADING):
                return await _answer(client, update, "Nothing to cancel")
            await _answer(client, update, "Cancelling…")
            job.request_cancel()  # cancels the real asyncio task -> TDLib / HTTP stop

        elif action is CallbackAction.SKIP_WAIT:
            if job.stage is not JobStage.PROCESSING:
                return await _answer(client, update, "Not processing")
            await _answer(client, update, "OK - link sent without waiting")
            job.skip_event.set()

        elif action is CallbackAction.DELETE:
            if not job.abyss_slug:
                return await _answer(client, update, "No Abyss file to delete", True)
            try:
                await app.abyss.delete_file(job.abyss_slug)
                await _answer(client, update, "Deleted from Abyss", True)
            except AbyssError as exc:
                await _answer(client, update, str(exc)[:190], True)

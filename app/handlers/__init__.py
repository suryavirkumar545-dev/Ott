"""Single message router (one update handler -> deterministic ordering)."""

from __future__ import annotations

import logging

import pytdbot

from app.config import config
from app.handlers import media, start, text
from app.services.telegram_service import send_text

logger = logging.getLogger(__name__)


def sender_id(message) -> int:
    sender = message.sender_id
    if isinstance(sender, pytdbot.types.MessageSenderUser):
        return sender.user_id or 0
    return 0


async def dispatch(app, message) -> None:
    if message is None or message.is_outgoing:
        return
    user_id = sender_id(message)
    if not user_id:
        return
    if not config.is_allowed(user_id):
        logger.warning("Blocked unauthorized user %s", user_id)
        await send_text(app.client, message.chat_id, "🔒 <b>Private bot</b>\n\nThis bot is for its owner only.")
        return
    # media first and synchronously creates the job, so album order = queue order
    if await media.handle(app, message, user_id):
        return
    if await start.handle(app, message, user_id):
        return
    await text.handle(app, message, user_id)

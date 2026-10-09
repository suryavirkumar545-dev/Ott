"""Fallback for plain text."""

from __future__ import annotations

import pytdbot

from app.services.telegram_service import send_text


async def handle(app, message, user_id: int) -> bool:
    content = message.content
    if isinstance(content, pytdbot.types.MessageText):
        await send_text(
            app.client, message.chat_id,
            "🎬 Send or forward a <b>video</b> and I will upload it to Abyss automatically.",
        )
        return True
    return False

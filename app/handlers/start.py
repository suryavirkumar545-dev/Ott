"""Commands: /start /help /queue /status."""

from __future__ import annotations

import pytdbot

from app.config import config
from app.services.telegram_service import send_text
from app.ui import messages


def _command(message) -> str | None:
    content = message.content
    if isinstance(content, pytdbot.types.MessageText) and content.text is not None:
        text = (content.text.text or "").strip()
        if text.startswith("/"):
            return text.split()[0].lstrip("/").split("@")[0].lower()
    return None


async def _first_name(client, user_id: int) -> str | None:
    try:
        user = await client.getUser(user_id=user_id)
    except Exception:  # noqa: BLE001
        return None
    return None if isinstance(user, pytdbot.types.Error) else getattr(user, "first_name", None)


async def handle(app, message, user_id: int) -> bool:
    command = _command(message)
    if command is None:
        return False
    client, chat = app.client, message.chat_id
    if command == "start":
        name = await _first_name(client, user_id)
        await send_text(client, chat, messages.start_message(name, config.max_file_size_mb, config.restrict_to_admin))
    elif command == "help":
        await send_text(client, chat, messages.help_message(config.max_file_size_mb))
    elif command in ("queue", "status"):
        mine = [j for j in app.progress.active_jobs() if j.owner_user_id == user_id]
        await send_text(client, chat, messages.queue_view(mine))
    else:
        return False
    return True

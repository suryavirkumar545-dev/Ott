"""Telegram helpers: media extraction and message sending/editing."""

from __future__ import annotations

import logging
import os

import pytdbot

from app.services.cleanup_service import sanitize_filename

logger = logging.getLogger(__name__)
T = pytdbot.types

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts",
    ".mpg", ".mpeg", ".3gp", ".ogv", ".mts", ".m2ts",
}


class UnsupportedMedia(Exception):
    pass


def _size(file) -> int:
    return int(getattr(file, "size", 0) or getattr(file, "expected_size", 0) or 0)


def extract_media(message) -> dict | None:
    """Normalised info for a video / video-document message, else ``None``.

    Raises :class:`UnsupportedMedia` for documents that are not videos.
    """
    content = message.content
    if content is None:
        return None

    if isinstance(content, T.MessageVideo):
        video = content.video
        file = getattr(video, "video", None)
        if file is None:
            return None
        name = getattr(video, "file_name", "") or f"video_{message.id}.mp4"
        return {
            "file_id": file.id,
            "file_name": sanitize_filename(name, "video.mp4"),
            "file_size": _size(file),
            "mime_type": getattr(video, "mime_type", "") or "video/mp4",
            "duration": getattr(video, "duration", 0) or 0,
            "width": getattr(video, "width", 0) or 0,
            "height": getattr(video, "height", 0) or 0,
            "is_video": True,
        }

    if isinstance(content, T.MessageDocument):
        document = content.document
        file = getattr(document, "document", None)
        if file is None:
            return None
        name = getattr(document, "file_name", "") or f"file_{message.id}"
        mime = getattr(document, "mime_type", "") or ""
        ext = os.path.splitext(name)[1].lower()
        if not (mime.startswith("video/") or ext in VIDEO_EXTENSIONS):
            raise UnsupportedMedia("not a video")
        if "." not in name:
            name += ".mp4"
        return {
            "file_id": file.id,
            "file_name": sanitize_filename(name),
            "file_size": _size(file),
            "mime_type": mime if mime.startswith("video/") else "video/mp4",
            "duration": 0,
            "width": 0,
            "height": 0,
            "is_video": True,
        }
    return None


async def send_text(client, chat_id: int, text: str, markup=None):
    """Send an HTML message. Returns the Message, or the Error object."""
    try:
        return await client.sendTextMessage(
            chat_id=chat_id,
            text=text,
            parse_mode="html",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("sendTextMessage raised: %s", exc)
        return None


async def edit_text(client, chat_id: int, message_id: int, text: str, markup=None):
    """Edit an HTML message. Returns the Message, or the Error object."""
    try:
        return await client.editTextMessage(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="html",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("editTextMessage raised: %s", exc)
        return None


def is_error(result) -> bool:
    return result is None or isinstance(result, T.Error)

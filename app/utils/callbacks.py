"""Compact callback data (``action:job_id``), well under Telegram's 64 bytes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CallbackAction(str, Enum):
    CANCEL_QUEUED = "q"
    CANCEL_DOWNLOAD = "d"
    CANCEL_UPLOAD = "x"
    SKIP_WAIT = "s"
    DELETE = "r"


@dataclass(frozen=True)
class CallbackData:
    action: CallbackAction
    job_id: str


def encode(action: CallbackAction, job_id: str) -> bytes:
    data = f"{action.value}:{job_id}".encode("utf-8")
    if len(data) > 64:
        raise ValueError("callback data too long")
    return data


def decode(data: bytes | str | None) -> CallbackData | None:
    if not data:
        return None
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")
    head, _, job_id = data.partition(":")
    try:
        action = CallbackAction(head)
    except ValueError:
        return None
    if not job_id or len(job_id) > 32 or not job_id.isalnum():
        return None
    return CallbackData(action=action, job_id=job_id)

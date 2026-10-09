"""Inline keyboards. Button colours are applied only if TDLib supports them."""

from __future__ import annotations

import pytdbot

from app.models.job import Job
from app.utils.callbacks import CallbackAction, encode

T = pytdbot.types


def _style(name: str):
    cls = getattr(T, name, None)
    if cls is None:
        return None
    try:
        return cls()
    except Exception:  # noqa: BLE001
        return None


def _button(text: str, kind, style_name: str | None = None):
    style = _style(style_name) if style_name else None
    if style is not None:
        try:
            return T.InlineKeyboardButton(text=text, type=kind, style=style)
        except Exception:  # noqa: BLE001
            pass
    return T.InlineKeyboardButton(text=text, type=kind)


def _cb(text: str, action: CallbackAction, job: Job, style: str | None = None):
    return _button(
        text, T.InlineKeyboardButtonTypeCallback(data=encode(action, job.job_id)), style
    )


def _markup(rows):
    return T.ReplyMarkupInlineKeyboard(rows=rows)


def cancel_queued(job: Job):
    return _markup([[_cb("❌ Cancel", CallbackAction.CANCEL_QUEUED, job, "ButtonStyleDanger")]])


def cancel_download(job: Job):
    return _markup(
        [[_cb("⛔ Cancel Download", CallbackAction.CANCEL_DOWNLOAD, job, "ButtonStyleDanger")]]
    )


def cancel_upload(job: Job):
    return _markup(
        [[_cb("⛔ Cancel Upload", CallbackAction.CANCEL_UPLOAD, job, "ButtonStyleDanger")]]
    )


def skip_wait(job: Job):
    return _markup([[_cb("⏭ Don't Wait", CallbackAction.SKIP_WAIT, job)]])


def result(job: Job, allow_delete: bool = False):
    rows = []
    url = job.watch_url
    if url:
        rows.append(
            [
                _button("▶️ Watch", T.InlineKeyboardButtonTypeUrl(url=url), "ButtonStylePrimary"),
                _button("📋 Copy URL", T.InlineKeyboardButtonTypeCopyText(text=url)),
            ]
        )
    second = []
    if job.page_url and job.page_url != url:
        second.append(_button("🔗 Abyss Page", T.InlineKeyboardButtonTypeUrl(url=job.page_url)))
    if job.iframe_url:
        embed = f'<iframe src="{job.iframe_url}" width="100%" height="100%" frameborder="0" allowfullscreen></iframe>'
        second.append(_button("🧩 Embed Code", T.InlineKeyboardButtonTypeCopyText(text=embed)))
    if second:
        rows.append(second)
    if allow_delete and job.abyss_slug:
        rows.append([_cb("🗑 Delete from Abyss", CallbackAction.DELETE, job, "ButtonStyleDanger")])
    return _markup(rows) if rows else None

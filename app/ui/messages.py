"""Message builders (Telegram HTML parse mode).

Design: bold sans-serif headings, small-caps labels, a fixed-width progress
bar, one short block per stage.  Every dynamic value is HTML-escaped.
"""

from __future__ import annotations

import time

from pytdbot.utils import escape_html

from app.models.job import Job
from app.utils.fonts import bold, small_caps
from app.utils.formatters import (
    format_duration,
    format_eta,
    format_size,
    pretty_name,
    progress_bar,
)

DIV = "━━━━━━━━━━━━━━━━━━"
BRAND = "RS ABYSS UPLOADER BOT"


def esc(value: object) -> str:
    return "" if value is None else escape_html(str(value))


def _title(icon: str, text: str, step: int | None = None) -> str:
    line = f"{icon} <b>{bold(text.upper())}</b>"
    if step:
        line += f"   <i>{small_caps('step')} {step}/3</i>"
    return line


def _row(icon: str, label: str, value: str) -> str:
    return f"{icon} {small_caps(label)}  <b>{value}</b>"


def _file_line(job: Job) -> str:
    return f"🎬 <b>{esc(pretty_name(job.file_name))}</b>"


def _foot(job: Job) -> str:
    return f"<i>#{job.job_id}</i>"


def _eta(done: int, total: int, speed: float) -> str:
    if speed > 0 and total > done:
        return format_eta((total - done) / speed)
    return "--:--"


# --------------------------------------------------------------------- #
# Welcome / help
# --------------------------------------------------------------------- #
def start_message(first_name: str | None, max_mb: int, admin_only: bool) -> str:
    hello = f"Hello, <b>{esc(first_name)}</b> 👋" if first_name else "Welcome 👋"
    lines = [
        f"🎬 <b>{bold(BRAND)}</b>",
        f"<i>{small_caps('telegram → abyss.to')}</i>",
        DIV,
        hello,
        "",
        "Send or forward a <b>video</b> and it is uploaded to Abyss "
        "automatically. Several files? They run <b>one by one</b>.",
        "",
        _row("📦", "max size", f"{max_mb} MB"),
        _row("🔄", "live updates", "every 5s"),
        "",
        f"{small_caps('commands')}  /queue · /help",
    ]
    if admin_only:
        lines += ["", "🔒 <i>Private bot · admin only</i>"]
    return "\n".join(lines)


def help_message(max_mb: int) -> str:
    return "\n".join(
        [
            f"📖 <b>{bold('HOW IT WORKS')}</b>",
            DIV,
            "1️⃣  Send or forward a video / video file",
            "2️⃣  Bot downloads it from Telegram",
            "3️⃣  Bot uploads it to Abyss",
            "4️⃣  You get the watch link",
            "",
            _row("📦", "max size", f"{max_mb} MB"),
            "⛔ Use the cancel button under any progress message.",
            "🧹 Temporary files are deleted automatically.",
            "",
            f"{small_caps('commands')}  /queue · /help",
        ]
    )


# --------------------------------------------------------------------- #
# Pipeline stages
# --------------------------------------------------------------------- #
def queued(job: Job, position: int, total: int, active_name: str | None) -> str:
    lines = [
        _title("⏳", "queued"),
        DIV,
        _file_line(job),
        _row("📦", "size", format_size(job.file_size)),
        "",
        _row("🔢", "position", f"{position} of {total}"),
    ]
    if active_name:
        lines.append(f"<i>Now processing: {esc(pretty_name(active_name, 34))}</i>")
    lines += ["", _foot(job)]
    return "\n".join(lines)


def downloading(job: Job) -> str:
    done, total = job.downloaded_bytes, job.total_bytes
    return "\n".join(
        [
            _title("📥", "downloading", 1),
            DIV,
            _file_line(job),
            "",
            progress_bar(done, total),
            "",
            _row("📦", "done", f"{format_size(done)} / {format_size(total)}"),
            _row("⚡", "speed", f"{format_size(job.download_speed)}/s"),
            _row("⏳", "eta", _eta(done, total, job.download_speed)),
            _row("🕒", "elapsed", format_duration(job.elapsed)),
            "",
            _foot(job),
        ]
    )


def uploading(job: Job) -> str:
    done, total = job.uploaded_bytes, job.total_bytes
    elapsed = (
        format_duration(time.time() - job.upload_started_at)
        if job.upload_started_at
        else "00:00"
    )
    return "\n".join(
        [
            _title("☁️", "uploading to abyss", 2),
            DIV,
            _file_line(job),
            "",
            progress_bar(done, total),
            "",
            _row("📦", "sent", f"{format_size(done)} / {format_size(total)}"),
            _row("⚡", "speed", f"{format_size(job.upload_speed)}/s"),
            _row("⏳", "eta", _eta(done, total, job.upload_speed)),
            _row("🕒", "elapsed", elapsed),
            "",
            _foot(job),
        ]
    )


def processing(job: Job) -> str:
    status = (job.abyss_status or "processing").title()
    waited = int(job.processing_elapsed // 15 * 15)  # coarse clock = fewer edits
    return "\n".join(
        [
            _title("⚙️", "abyss processing", 3),
            DIV,
            _file_line(job),
            _row("📦", "size", format_size(job.file_size)),
            "",
            _row("📡", "status", esc(status)),
            _row("🕒", "waiting", format_duration(waited)),
            "",
            "<i>Abyss is preparing your video. The queue keeps moving.</i>",
            "",
            _foot(job),
        ]
    )


def completed(job: Job) -> str:
    lines = [
        _title("✅", "upload complete"),
        DIV,
        _file_line(job),
        f"📦 {format_size(job.file_size)}  ·  🕒 {format_duration(job.elapsed)}",
    ]
    if job.skipped_wait:
        lines += ["", "⏳ <i>Abyss is still processing — the link works once it is ready.</i>"]
    url = job.watch_url
    if url:
        lines += ["", f"▶️ <b>{small_caps('watch url')}</b>", f"<code>{esc(url)}</code>"]
    if job.page_url and job.page_url != url:
        lines += ["", f"🔗 <b>{small_caps('abyss page')}</b>", f"<code>{esc(job.page_url)}</code>"]
    if job.direct_url and job.direct_url not in (url, job.page_url):
        lines += ["", f"⬇️ <b>{small_caps('direct url')}</b>", f"<code>{esc(job.direct_url)}</code>"]
    if not url and not job.page_url and not job.direct_url:
        lines += ["", "<i>Abyss did not return a URL. Check your Abyss dashboard.</i>"]
    lines += ["", _foot(job)]
    return "\n".join(lines)


def cancelled(job: Job) -> str:
    stage = job.cancelled_stage or "upload"
    lines = [
        _title("❌", f"{stage} cancelled"),
        DIV,
        _file_line(job),
        "",
        "🧹 <i>Temporary files were removed.</i>",
        "",
        _foot(job),
    ]
    return "\n".join(lines)


def failed(job: Job) -> str:
    return "\n".join(
        [
            _title("⚠️", "upload failed"),
            DIV,
            _file_line(job),
            "",
            f"{small_caps('reason')}",
            f"<i>{esc(job.error or 'Unknown error')}</i>",
            "",
            "🔁 Send the file again to retry.",
            "",
            _foot(job),
        ]
    )


# --------------------------------------------------------------------- #
# Misc
# --------------------------------------------------------------------- #
_ICON = {
    "queued": "⏳",
    "downloading": "📥",
    "uploading": "☁️",
    "processing": "⚙️",
    "done": "✅",
    "cancelled": "❌",
    "failed": "⚠️",
}


def queue_view(jobs: list[Job]) -> str:
    if not jobs:
        return f"📋 <b>{bold('UPLOAD QUEUE')}</b>\n{DIV}\n\n<i>Nothing in the queue.</i>"
    lines = [f"📋 <b>{bold('UPLOAD QUEUE')}</b>", DIV]
    for index, job in enumerate(jobs, start=1):
        lines.append(
            f"{index}. {_ICON.get(job.stage.value, '•')} "
            f"{esc(pretty_name(job.file_name, 34))} — <i>{small_caps(job.stage.value)}</i>"
        )
    return "\n".join(lines)


def too_large(name: str, size: int, limit_mb: int) -> str:
    return "\n".join(
        [
            _title("⚠️", "file too large"),
            DIV,
            f"🎬 <b>{esc(pretty_name(name))}</b>",
            _row("📦", "size", format_size(size)),
            _row("🚫", "limit", f"{limit_mb} MB"),
        ]
    )


def unsupported() -> str:
    return "\n".join(
        [
            _title("⚠️", "unsupported file"),
            DIV,
            "Only <b>video</b> files are supported (mp4, mkv, avi, mov, webm…).",
        ]
    )

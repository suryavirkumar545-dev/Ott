"""Abyss.to API client (aiohttp).

Endpoints (from the Abyss dashboard API document):

* ``GET  {api}/v1/about?key=KEY``          quotas / max upload size
* ``POST {upload}/KEY``  (multipart)       upload  -> {status, slug, urlIframe, ...}
* ``GET  {api}/v1/files/{slug}?key=KEY``   file info / processing status
* ``DELETE {api}/v1/files/{slug}``         needs a dashboard JWT (optional)

The upload body is streamed from disk in 1 MB chunks, so RAM use stays flat even
for 2 GB files, and the client-side progress is real.  Cancelling the asyncio
task closes the HTTP connection immediately.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import random
import time
import uuid
from pathlib import Path
from typing import Awaitable, Callable

import aiohttp

from app.config import Config
from app.utils.formatters import format_size

logger = logging.getLogger(__name__)

ProgressCb = Callable[[int, int, float], Awaitable[None] | None]

READY_STATUSES = {"ready", "public", "raw", "completed", "done"}
FAILED_STATUSES = {"banned", "error", "failed"}


class AbyssError(RuntimeError):
    """Error whose message is safe to show to the user."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class AbyssAuthError(AbyssError):
    pass


class AbyssRateLimitError(AbyssError):
    def __init__(self, message: str, retry_after: float = 5.0):
        super().__init__(message, status=429, retryable=True)
        self.retry_after = retry_after


def _backoff(attempt: int) -> float:
    return min(60.0, 2.0**attempt + random.uniform(0, 1))


def _retry_after(headers) -> float:
    try:
        return min(120.0, max(1.0, float(headers.get("Retry-After", "5"))))
    except (TypeError, ValueError):
        return 5.0


def _http_error(status: int) -> AbyssError:
    if status in (401, 403):
        return AbyssAuthError("Abyss rejected the API key. Check ABYSS_API_KEY in config.py.", status=status)
    if status == 413:
        return AbyssError("Abyss says the file is too large.", status=status)
    if status == 415:
        return AbyssError("Abyss does not support this file format.", status=status)
    if status == 429:
        return AbyssRateLimitError("Abyss rate limit reached.")
    if status >= 500:
        return AbyssError(f"Abyss server error ({status}). Try again later.", status=status, retryable=True)
    return AbyssError(f"Abyss rejected the request ({status}).", status=status)


class AbyssService:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self._jwt: str | None = None
        self._about: tuple[float, dict] | None = None

    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": "sk-abyss-uploader/2.0"}
            )

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            raise RuntimeError("AbyssService.start() was not called")
        return self._session

    def _params(self, extra: dict | None = None) -> dict:
        params = {"key": self._config.abyss_api_key}
        if extra:
            params.update(extra)
        return params

    # ------------------------------------------------------------------ #
    async def _json(self, method: str, url: str, *, params=None, data=None,
                    headers=None, retries: int = 3) -> dict:
        """JSON request with 429 / network backoff."""
        for attempt in range(retries + 1):
            try:
                async with self.session.request(
                    method, url, params=params, data=data, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self._config.abyss_timeout),
                ) as response:
                    body = await response.text()
                    if response.status == 429:
                        raise AbyssRateLimitError(
                            "Abyss rate limit reached.", _retry_after(response.headers)
                        )
                    if response.status >= 400:
                        raise _http_error(response.status)
                    if not body:
                        return {}
                    try:
                        parsed = json.loads(body)
                    except json.JSONDecodeError:
                        return {"raw": body}
                    return parsed if isinstance(parsed, dict) else {"data": parsed}
            except AbyssRateLimitError as exc:
                if attempt >= retries:
                    raise
                wait = max(exc.retry_after, _backoff(attempt))
                logger.warning("Abyss 429 - waiting %.1fs (attempt %d)", wait, attempt + 1)
                await asyncio.sleep(wait)
            except AbyssError as exc:
                if not exc.retryable or attempt >= retries:
                    raise
                await asyncio.sleep(_backoff(attempt))
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt >= retries:
                    raise AbyssError("Could not reach Abyss (network error).", retryable=True) from exc
                await asyncio.sleep(_backoff(attempt))
        raise AbyssError("Abyss request failed.")

    # ------------------------------------------------------------------ #
    async def about(self, max_age: float = 60.0) -> dict:
        now = time.monotonic()
        if self._about and now - self._about[0] < max_age:
            return self._about[1]
        data = await self._json("GET", f"{self._config.abyss_api_base}/v1/about", params=self._params())
        self._about = (now, data)
        return data

    async def check_capacity(self, size: int) -> None:
        """Fail early (before downloading) if the account cannot take the file."""
        try:
            info = await self.about()
        except AbyssAuthError:
            raise
        except AbyssError as exc:
            logger.warning("Capacity check skipped: %s", exc)
            return
        limit = info.get("maxUploadSize") or 0
        if isinstance(limit, (int, float)) and limit > 0 and size > limit:
            raise AbyssError(f"File is larger than your Abyss limit ({format_size(limit)}).")
        quota = info.get("uploadQuota") or {}
        remaining = quota.get("dailyUploadRemaining") if isinstance(quota, dict) else None
        if isinstance(remaining, (int, float)) and 0 < remaining < size:
            raise AbyssError(
                f"Daily Abyss upload quota is too low ({format_size(remaining)} left)."
            )

    async def get_file_info(self, slug: str) -> dict:
        return await self._json(
            "GET", f"{self._config.abyss_api_base}/v1/files/{slug}", params=self._params()
        )

    # ------------------------------------------------------------------ #
    async def upload(self, path: Path, filename: str, mime: str | None = None,
                     progress_cb: ProgressCb | None = None) -> dict:
        """Upload with retries on network errors / 5xx / 429."""
        attempts = 1 + max(0, self._config.abyss_upload_retries)
        for attempt in range(attempts):
            try:
                return await self._upload_once(Path(path), filename, mime, progress_cb)
            except AbyssRateLimitError as exc:
                if attempt + 1 >= attempts:
                    raise
                wait = max(exc.retry_after, _backoff(attempt))
                logger.warning("Upload 429 - waiting %.1fs", wait)
                await asyncio.sleep(wait)
            except AbyssError as exc:
                if not exc.retryable or attempt + 1 >= attempts:
                    raise
                logger.warning("Upload failed (%s) - retry %d", exc, attempt + 1)
                await asyncio.sleep(_backoff(attempt))
        raise AbyssError("Abyss upload failed.")

    async def _upload_once(self, path: Path, filename: str, mime: str | None,
                           progress_cb: ProgressCb | None) -> dict:
        await self.start()
        total = path.stat().st_size
        boundary = f"----RSAbyss{uuid.uuid4().hex}"
        safe_name = filename.replace('"', "_").replace("\r", "").replace("\n", "")
        mime = mime or mimetypes.guess_type(safe_name)[0] or "video/mp4"
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode()
        length = len(head) + total + len(tail)
        state = {"sent": 0, "t0": time.monotonic(), "speed": 0.0, "mark": (time.monotonic(), 0)}

        async def body():
            yield head
            with open(path, "rb") as handle:
                while True:
                    chunk = await asyncio.to_thread(handle.read, 1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
                    state["sent"] += len(chunk)
                    now = time.monotonic()
                    t_mark, b_mark = state["mark"]
                    if now - t_mark >= 1.0:
                        inst = (state["sent"] - b_mark) / (now - t_mark)
                        state["speed"] = inst if state["speed"] == 0 else 0.6 * state["speed"] + 0.4 * inst
                        state["mark"] = (now, state["sent"])
                    if progress_cb is not None:
                        res = progress_cb(state["sent"], total, state["speed"])
                        if asyncio.iscoroutine(res):
                            await res
            yield tail

        url = f"{self._config.abyss_upload_base}/{self._config.abyss_api_key}"
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(length),
        }
        try:
            async with self.session.post(
                url, data=body(), headers=headers,
                timeout=aiohttp.ClientTimeout(
                    total=None, connect=30, sock_connect=30,
                    sock_read=self._config.abyss_upload_response_timeout,
                ),
            ) as response:
                status = response.status
                retry_after = _retry_after(response.headers)
                text = await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as exc:
            logger.warning("Upload connection problem: %s", type(exc).__name__)
            raise AbyssError("Connection to Abyss was lost during upload.", retryable=True) from exc

        if status == 429:
            raise AbyssRateLimitError("Abyss rate limit reached.", retry_after)
        if status >= 400:
            raise _http_error(status)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AbyssError("Abyss returned an unreadable response.") from exc
        if not isinstance(payload, dict) or not payload.get("slug"):
            msg = payload.get("msg") if isinstance(payload, dict) else None
            raise AbyssError(f"Abyss rejected the upload{': ' + str(msg) if msg else '.'}")
        return payload

    # ------------------------------------------------------------------ #
    async def wait_until_ready(
        self, slug: str, cancel_event: asyncio.Event | None = None,
        skip_event: asyncio.Event | None = None,
        on_tick: Callable[[dict], None] | None = None,
    ) -> tuple[dict, bool]:
        """Poll until ready. Returns ``(info, skipped)``."""
        deadline = time.monotonic() + self._config.abyss_processing_timeout
        last: dict = {}
        failures = 0
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError("processing cancelled")
            if skip_event is not None and skip_event.is_set():
                return last, True
            try:
                last = await self.get_file_info(slug)
                failures = 0
            except AbyssAuthError:
                raise
            except AbyssError as exc:
                failures += 1
                logger.warning("Status check failed (%d): %s", failures, exc)
                if failures >= 5:
                    raise
            status = str(last.get("status", "")).lower()
            if on_tick is not None and last:
                on_tick(last)
            if status in READY_STATUSES:
                return last, False
            if status in FAILED_STATUSES:
                raise AbyssError(f"Abyss could not process the video (status: {status}).")
            if time.monotonic() >= deadline:
                raise AbyssError("Abyss processing timed out.")
            await self._sleep_or_event(
                self._config.abyss_poll_interval + random.uniform(0, 1.5), skip_event
            )

    @staticmethod
    async def _sleep_or_event(seconds: float, event: asyncio.Event | None) -> None:
        if event is None:
            await asyncio.sleep(seconds)
            return
        try:
            await asyncio.wait_for(event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    # ------------------------------------------------------------------ #
    async def _login(self) -> str | None:
        if self._jwt:
            return self._jwt
        if not (self._config.abyss_email and self._config.abyss_password):
            return None
        data = await self._json(
            "POST", f"{self._config.abyss_api_base}/auth/login",
            data=json.dumps({"email": self._config.abyss_email, "password": self._config.abyss_password}),
            headers={"Content-Type": "application/json"},
        )
        self._jwt = data.get("token")
        return self._jwt

    async def delete_file(self, slug: str) -> bool:
        await self.start()
        token = await self._login()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            await self._json(
                "DELETE", f"{self._config.abyss_api_base}/v1/files/{slug}",
                params=self._params(), headers=headers,
            )
            return True
        except AbyssAuthError as exc:
            self._jwt = None
            raise AbyssAuthError("Delete needs ABYSS_EMAIL / ABYSS_PASSWORD in config.py.") from exc

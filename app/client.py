"""Application wiring: Pytdbot client + services + handlers."""

from __future__ import annotations

import logging

import pytdbot

from app.config import config
from app.handlers import callbacks as callbacks_handler
from app.handlers import dispatch
from app.services.abyss_service import AbyssError, AbyssService
from app.services.cleanup_service import CleanupService
from app.services.download_service import DownloadService
from app.services.progress_service import ProgressService
from app.services.queue_service import QueueService
from app.services.upload_service import UploadService

logger = logging.getLogger(__name__)


class BotApp:
    def __init__(self) -> None:
        self.config = config
        config.prepare()
        self.delete_enabled = bool(config.abyss_email and config.abyss_password)
        self.effective_limit_bytes = config.max_file_size_bytes

        self.client = pytdbot.Client(
            token=config.bot_token,
            api_id=config.api_id,
            api_hash=config.api_hash,
            user_bot=True,
            files_directory=str(config.files_dir),
            database_encryption_key=config.resolve_encryption_key(),
            default_parse_mode="html",
            td_verbosity=1,
        )

        self.abyss = AbyssService(config)
        self.downloads = DownloadService()
        self.cleanup = CleanupService(config)
        self.progress = ProgressService(self.client, config, allow_delete=self.delete_enabled)
        self.upload = UploadService(
            self.client, config, self.abyss, self.downloads, self.cleanup, self.progress
        )
        self.queue = QueueService(self.upload, self.progress, config.max_concurrent_jobs)
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self.client.on_updateFile()
        async def _on_file(client, update):
            self.downloads.on_file_update(update.file)

        @self.client.on_updateNewMessage()
        async def _on_message(client, update):
            try:
                await dispatch(self, update.message)
            except Exception:  # noqa: BLE001 - never let a handler kill the bot
                logger.exception("message handler error")

        callbacks_handler.register(self)

    async def start(self) -> None:
        swept = self.cleanup.sweep_stale()
        await self.abyss.start()
        await self._learn_abyss_limits()
        await self.progress.start()
        await self.queue.start()
        logger.info("Ready (workers=%d, stale files removed=%d)", config.max_concurrent_jobs, swept)

    async def _learn_abyss_limits(self) -> None:
        try:
            about = await self.abyss.about()
        except AbyssError as exc:
            logger.warning("Abyss /about failed at startup: %s", exc)
            return
        limit = about.get("maxUploadSize") or 0
        if isinstance(limit, (int, float)) and 0 < limit < self.effective_limit_bytes:
            self.effective_limit_bytes = int(limit)
        logger.info("Abyss reachable; effective max file size %d MB",
                    self.effective_limit_bytes // (1024 * 1024))

    async def run(self) -> None:
        await self.start()
        await self.client.run()

    async def stop(self) -> None:
        await self.queue.stop()
        await self.progress.stop()
        await self.abyss.close()
        try:
            await self.client.stop()
        except Exception:  # noqa: BLE001
            pass

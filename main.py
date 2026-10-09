"""RS ABYSS UPLOADER BOT - entry point.

    python main.py            run the bot
    python main.py --check    validate config.py and test the Abyss API key
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.config import config
from app.logging_config import setup_logging

logger = logging.getLogger("main")


async def _check() -> int:
    from app.services.abyss_service import AbyssService
    from app.utils.formatters import format_size

    config.prepare()
    abyss = AbyssService(config)
    await abyss.start()
    try:
        about = await abyss.about(max_age=0)
        quota = about.get("uploadQuota") or {}
        print("Abyss API : OK")
        print("Max upload:", format_size(about.get("maxUploadSize", 0)))
        print("Daily left:", format_size(quota.get("dailyUploadRemaining", 0)))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Abyss API : FAILED - {exc}")
        return 2
    finally:
        await abyss.close()


async def _run() -> None:
    from app.client import BotApp

    app = BotApp()
    try:
        await app.run()
    finally:
        await app.stop()


def main() -> int:
    setup_logging(config.secrets_list)
    if "--check" in sys.argv:
        return asyncio.run(_check())
    logger.info("Starting SK Abyss Uploader Bot")
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

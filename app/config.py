"""Project configuration.

Everything lives right here in this file - there is NO ``.env`` file and NO
environment-variable lookup.  Edit the values below and restart the bot.

SECURITY: this file contains secrets.  Never upload it to a public repository,
and rotate the tokens if the file is ever shared.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ======================================================================== #
#  1. CREDENTIALS  (edit these)
# ======================================================================== #
BOT_TOKEN = "8288408514:AAFgHpFzYLNilxFHVcqepfDVydvkPRb5Rrw"
API_ID = 33882007
API_HASH = "799677df02c75c218e83f74a70c1eef9"
ABYSS_API_KEY = "1ea21a974457135ef4e462b878d2be09"

# ======================================================================== #
#  2. ACCESS CONTROL
# ======================================================================== #
ADMIN_ID = 6881329740,7033830081          # only this Telegram user id can use the bot
RESTRICT_TO_ADMIN = True       # False = anyone can use the bot

# ======================================================================== #
#  3. LIMITS & BEHAVIOUR
# ======================================================================== #
MAX_FILE_SIZE_MB = 2000        # hard safety limit (Telegram bot limit is 2000 MB)
PROGRESS_UPDATE_INTERVAL = 5   # seconds between progress-message edits
MAX_CONCURRENT_JOBS = 1        # files downloaded/uploaded at the same time
MAX_PROCESSING_WATCHERS = 5    # files whose Abyss processing is polled at once

# ======================================================================== #
#  4. ABYSS API
# ======================================================================== #
ABYSS_API_BASE = "https://api.abyss.to"
ABYSS_UPLOAD_BASE = "http://up.abyss.to"   # documented upload host
ABYSS_TIMEOUT = 60                  # seconds, normal API calls
ABYSS_UPLOAD_RESPONSE_TIMEOUT = 900  # seconds to wait for Abyss' reply after the body is sent
ABYSS_UPLOAD_RETRIES = 2            # extra attempts after a network error / 5xx
ABYSS_PROCESSING_TIMEOUT = 1800     # seconds to wait for "ready"
ABYSS_POLL_INTERVAL = 10            # seconds between status checks

# Optional - only needed for the "Delete from Abyss" button (JWT endpoint).
ABYSS_EMAIL = "suryavirkumar545@gmail.com"
ABYSS_PASSWORD = "SURYAVIR@987654321"

# ======================================================================== #
#  5. PATHS
# ======================================================================== #
TEMP_DIR = PROJECT_ROOT / "temp"
TDLIB_FILES_DIR = PROJECT_ROOT / "tdlib_files"
TDLIB_SESSION_DIR = PROJECT_ROOT / "tdlib_session"


@dataclass(frozen=True)
class Config:
    # credentials
    bot_token: str = BOT_TOKEN
    api_id: int = API_ID
    api_hash: str = API_HASH
    abyss_api_key: str = ABYSS_API_KEY
    # access
    admin_id: int = ADMIN_ID
    restrict_to_admin: bool = RESTRICT_TO_ADMIN
    # limits
    max_file_size_mb: int = MAX_FILE_SIZE_MB
    progress_update_interval: int = PROGRESS_UPDATE_INTERVAL
    max_concurrent_jobs: int = MAX_CONCURRENT_JOBS
    max_processing_watchers: int = MAX_PROCESSING_WATCHERS
    # abyss
    abyss_api_base: str = ABYSS_API_BASE
    abyss_upload_base: str = ABYSS_UPLOAD_BASE
    abyss_timeout: int = ABYSS_TIMEOUT
    abyss_upload_response_timeout: int = ABYSS_UPLOAD_RESPONSE_TIMEOUT
    abyss_upload_retries: int = ABYSS_UPLOAD_RETRIES
    abyss_processing_timeout: int = ABYSS_PROCESSING_TIMEOUT
    abyss_poll_interval: int = ABYSS_POLL_INTERVAL
    abyss_email: str = ABYSS_EMAIL
    abyss_password: str = ABYSS_PASSWORD
    # paths
    temp_dir: Path = TEMP_DIR
    files_dir: Path = TDLIB_FILES_DIR
    session_dir: Path = TDLIB_SESSION_DIR

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def secrets_list(self) -> list[str]:
        return [self.bot_token, self.api_hash, self.abyss_api_key, self.abyss_password]

    def is_allowed(self, user_id: int) -> bool:
        if not self.restrict_to_admin:
            return True
        return self.admin_id != 0 and user_id == self.admin_id

    def prepare(self) -> None:
        """Validate the values and create the working directories."""
        if not self.bot_token or ":" not in self.bot_token:
            raise RuntimeError("config.py: BOT_TOKEN is missing or malformed")
        if self.api_id <= 0 or not self.api_hash:
            raise RuntimeError("config.py: API_ID / API_HASH are missing")
        if not self.abyss_api_key:
            raise RuntimeError("config.py: ABYSS_API_KEY is missing")
        for folder in (self.temp_dir, self.files_dir, self.session_dir):
            folder.mkdir(parents=True, exist_ok=True)

    def resolve_encryption_key(self) -> str:
        """Stable TDLib database key stored next to the session (never logged)."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        key_file = self.session_dir / ".tdlib_key"
        if key_file.exists():
            return key_file.read_text().strip()
        key = secrets.token_hex(32)
        key_file.write_text(key)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return key


config = Config()

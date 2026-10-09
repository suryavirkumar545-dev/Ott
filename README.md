# RS ABYSS UPLOADER BOT

Telegram → Abyss.to uploader built with **Pytdbot + TDLib** (asyncio, aiohttp).

Send/forward a video → TDLib download → streamed upload to Abyss → watch URL.
Several files are queued and processed one after another.

## Setup
1. Open `app/config.py` and fill `BOT_TOKEN`, `API_ID`, `API_HASH`, `ABYSS_API_KEY`, `ADMIN_ID`.
   (No `.env`, no environment variables.)
2. `pip install -r requirements.txt`
3. `python main.py --check`   # tests the Abyss key
4. `python main.py`

## Behaviour
* Download progress comes from TDLib; upload progress is measured while streaming the file (1 MB chunks, no RAM spike).
* One progress message per job, edited every 5 s (immediate on stage change).
* ⛔ Cancel stops the real TDLib download / HTTP upload and deletes temp files.
* After the upload the queue moves on; Abyss processing is awaited in the background, and the final message carries the URLs Abyss really returned (`urlIframe`, `url`, optional direct URL).
* "⏭ Don't Wait" sends the link before Abyss finishes processing.
* Temp files are removed on success, failure, cancel and at startup.

## Notes
* Max size 2000 MB (also capped by your Abyss `maxUploadSize`).
* Delete button only appears if `ABYSS_EMAIL` / `ABYSS_PASSWORD` are set (Abyss needs a dashboard login for deletion).
* Tests: `pip install -r requirements-dev.txt && pytest`
* Keep `config.py` private; rotate tokens if it was ever shared.

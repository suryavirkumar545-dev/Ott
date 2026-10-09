from pathlib import Path

from app.services.cleanup_service import sanitize_filename


def test_sanitize():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("a<b>c.mkv") == "a_b_c.mkv"
    assert sanitize_filename("") == "file.mp4"

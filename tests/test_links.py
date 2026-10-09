from app.models.job import Job
from app.services.upload_service import apply_links


def _job():
    return Job(owner_user_id=1, chat_id=1, file_id=1, file_name="a.mp4", file_size=1)


def test_only_real_urls():
    job = _job()
    apply_links(job, {"urlIframe": "https://abyss.to/e/x", "url": "javascript:alert(1)"})
    assert job.watch_url == "https://abyss.to/e/x"
    assert job.page_url is None and job.direct_url is None

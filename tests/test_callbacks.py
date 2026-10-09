from app.utils.callbacks import CallbackAction, decode, encode


def test_roundtrip():
    data = encode(CallbackAction.CANCEL_UPLOAD, "8f32a1bc")
    assert len(data) < 64
    cb = decode(data)
    assert cb.action is CallbackAction.CANCEL_UPLOAD and cb.job_id == "8f32a1bc"


def test_bad_data():
    assert decode(b"zz:1234") is None
    assert decode(b"d:") is None
    assert decode(b"d:../etc") is None
    assert decode(None) is None

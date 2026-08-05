"""test_extract.py — durable pytest coverage for extraction robustness.

Vision-path 429/5xx retry (qwen_vision) and the lh download size ladder
(dom_extract). Both were fixed live; these tests lock them in.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from menuflation.extract import qwen_vision  # noqa: E402


class _FakeResp:
    content = b"x"

    def __init__(self, code, body=None):
        self.status_code = code
        self.text = "rate limited" if code == 429 else ""
        self._body = body

    def json(self):
        return self._body


def _ok_body():
    return {"usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "choices": [{"message": {"content": '{"is_menu": true, '
                                               '"currency_iso": "USD", '
                                               '"items": [{"name": "Burger", '
                                               '"price": 7.95}]}'}}]}


def test_vision_retries_on_429(monkeypatch, tmp_path):
    """extract_menu_photo must back off and retry transient 429s (3 attempts)."""
    calls = {"n": 0}
    real_post = qwen_vision.requests.post

    def fake_post(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            return _FakeResp(429)
        return _FakeResp(200, _ok_body())

    monkeypatch.setattr(qwen_vision.requests, "post", fake_post)
    try:
        img = tmp_path / "x.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0 fake jpeg bytes")
        res = qwen_vision.extract_menu_photo(str(img))
        assert calls["n"] == 3, f"expected 3 attempts, got {calls['n']}"
        assert res["data"]["items"][0]["price"] == 7.95, res
    finally:
        monkeypatch.setattr(qwen_vision.requests, "post", real_post)


def test_download_lh_size_ladder(monkeypatch, tmp_path):
    """Small originals reject s1600 upscale — must fall down the ladder."""
    import dom_extract

    got = {"sizes": []}

    def fake_get(url, timeout=60):
        for s in dom_extract.SIZES:
            if url.endswith(s):
                got["sizes"].append(s)
                if s == dom_extract.SIZES[0]:
                    return _FakeResp(400)
                return _FakeResp(200, {"bytes": 1})
        return _FakeResp(404)

    monkeypatch.setattr(dom_extract.requests, "get", fake_get)
    dest = tmp_path / "p.jpg"
    dom_extract.download_lh("TOKEN", str(dest))
    assert got["sizes"] == [dom_extract.SIZES[0], dom_extract.SIZES[1]], got
    assert dest.exists() and dest.stat().st_size == 1

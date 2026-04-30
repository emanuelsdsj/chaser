import json as _json

import pytest

from chaser.net.headers import Headers
from chaser.net.response import Response


def resp(**kwargs: object) -> Response:
    defaults: dict = {
        "url": "https://example.com",
        "status": 200,
        "headers": Headers({"content-type": "text/html"}),
        "body": b"<html>hello</html>",
    }
    return Response(**{**defaults, **kwargs})


def test_text_utf8():
    r = resp(body=b"hello world", encoding="utf-8")
    assert r.text == "hello world"


def test_text_latin1():
    r = resp(body="café".encode("latin-1"), encoding="latin-1")
    assert r.text == "café"


def test_text_bad_bytes_replaced():
    r = resp(body=b"\xff\xfe bad", encoding="utf-8")
    assert isinstance(r.text, str)


def test_ok_2xx():
    assert resp(status=200).ok is True
    assert resp(status=201).ok is True
    assert resp(status=204).ok is True
    assert resp(status=299).ok is True


def test_ok_false_outside_2xx():
    assert resp(status=301).ok is False
    assert resp(status=400).ok is False
    assert resp(status=404).ok is False
    assert resp(status=500).ok is False


def test_json_valid():
    payload = {"key": "value", "n": 42, "flag": True}
    r = resp(body=_json.dumps(payload).encode())
    assert r.json() == payload


def test_json_invalid_raises():
    r = resp(body=b"not valid json {{")
    with pytest.raises((ValueError, _json.JSONDecodeError)):
        r.json()


def test_headers_coerced_from_dict():
    r = resp(headers={"Content-Type": "text/plain", "X-Token": "abc"})
    assert isinstance(r.headers, Headers)
    assert r.headers["content-type"] == "text/plain"
    assert r.headers["x-token"] == "abc"


def test_elapsed_default():
    r = resp()
    assert r.elapsed == 0.0


def test_elapsed_custom():
    r = resp(elapsed=1.234)
    assert r.elapsed == pytest.approx(1.234)


def test_repr_contains_status_and_url():
    r = resp(status=404, url="https://example.com/missing")
    assert "404" in repr(r)
    assert "example.com" in repr(r)


def test_request_reference_none_by_default():
    r = resp()
    assert r.request is None


def test_urljoin_absolute_path():
    r = resp(url="https://example.com/blog/post-1")
    assert r.urljoin("/about") == "https://example.com/about"


def test_urljoin_relative_path():
    r = resp(url="https://example.com/blog/")
    assert r.urljoin("post-2") == "https://example.com/blog/post-2"


def test_urljoin_already_absolute():
    r = resp(url="https://example.com/")
    assert r.urljoin("https://other.com/page") == "https://other.com/page"


def test_json_selector_jmespath():
    import json

    payload = {"products": [{"name": "widget", "price": 9.99}, {"name": "gadget", "price": 19.99}]}
    r = resp(body=json.dumps(payload).encode())
    names = r.json_selector.jmespath("products[*].name").getall()
    assert names == ["widget", "gadget"]


def test_json_selector_jmespath_nested():
    import json

    payload = {"store": {"books": [{"title": "A"}, {"title": "B"}]}}
    r = resp(body=json.dumps(payload).encode())
    titles = r.json_selector.jmespath("store.books[*].title").getall()
    assert titles == ["A", "B"]


def test_json_selector_jmespath_no_match():
    import json

    r = resp(body=json.dumps({"a": 1}).encode())
    assert r.json_selector.jmespath("missing.key").getall() == []

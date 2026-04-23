from chaser.net.headers import Headers
from chaser.net.request import Request


def test_defaults():
    r = Request(url="https://example.com")
    assert r.method == "GET"
    assert r.priority == 0
    assert r.use_browser is False
    assert r.body is None
    assert r.callback is None
    assert isinstance(r.headers, Headers)
    assert isinstance(r.meta, dict)
    assert r.meta == {}


def test_method_is_uppercased():
    r = Request(url="https://example.com", method="post")
    assert r.method == "POST"


def test_method_already_upper():
    r = Request(url="https://example.com", method="DELETE")
    assert r.method == "DELETE"


def test_headers_coerced_from_dict():
    r = Request(url="https://example.com", headers={"Content-Type": "application/json"})
    assert isinstance(r.headers, Headers)
    assert r.headers["content-type"] == "application/json"


def test_headers_already_headers_type():
    h = Headers({"accept": "text/html"})
    r = Request(url="https://example.com", headers=h)
    assert r.headers is h


def test_meta_not_shared_between_instances():
    r1 = Request(url="https://a.com")
    r2 = Request(url="https://b.com")
    r1.meta["key"] = "value"
    assert "key" not in r2.meta


def test_copy_produces_new_instance():
    r = Request(url="https://example.com", priority=5)
    r2 = r.copy(url="https://other.com", priority=10)
    assert r2.url == "https://other.com"
    assert r2.priority == 10
    assert r.url == "https://example.com"
    assert r.priority == 5


def test_copy_preserves_unoverridden_fields():
    r = Request(url="https://example.com", method="POST", use_browser=True)
    r2 = r.copy(priority=99)
    assert r2.method == "POST"
    assert r2.use_browser is True


def test_use_browser_flag():
    r = Request(url="https://example.com", use_browser=True)
    assert r.use_browser is True


def test_priority_ordering():
    low = Request(url="https://a.com", priority=1)
    high = Request(url="https://b.com", priority=10)
    # higher priority should sort first (min-heap: high < low)
    assert high < low


def test_repr():
    r = Request(url="https://example.com/page", method="GET")
    assert "GET" in repr(r)
    assert "example.com" in repr(r)

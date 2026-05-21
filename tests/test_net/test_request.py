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


# ---------------------------------------------------------------------------
# from_form
# ---------------------------------------------------------------------------


def test_from_form_encodes_body():
    r = Request.from_form("https://example.com/login", {"user": "alice", "pass": "secret"})
    assert r.body is not None
    body_str = r.body.decode()
    assert "user=alice" in body_str
    assert "pass=secret" in body_str


def test_from_form_sets_content_type():
    r = Request.from_form("https://example.com/submit", {"q": "hello"})
    assert r.headers.get("content-type") == "application/x-www-form-urlencoded"


def test_from_form_default_method_is_post():
    r = Request.from_form("https://example.com/", {"x": "1"})
    assert r.method == "POST"


def test_from_form_custom_headers_preserved():
    r = Request.from_form(
        "https://example.com/",
        {"x": "1"},
        headers={"x-csrf-token": "abc123"},
    )
    assert r.headers.get("x-csrf-token") == "abc123"
    assert r.headers.get("content-type") == "application/x-www-form-urlencoded"


def test_from_form_custom_method():
    r = Request.from_form("https://example.com/", {"x": "1"}, method="PUT")
    assert r.method == "PUT"


# ---------------------------------------------------------------------------
# serialisation round-trip
# ---------------------------------------------------------------------------


def test_to_dict_round_trip_minimal():
    r = Request(url="https://example.com/page")
    d = r.to_dict()
    r2 = Request.from_dict(d)
    assert r2.url == r.url
    assert r2.method == r.method
    assert r2.priority == r.priority
    assert r2.body is None
    assert r2.callback is None
    assert r2.use_browser is False


def test_to_dict_round_trip_full():
    r = Request(
        url="https://example.com/submit",
        method="POST",
        headers={"content-type": "application/json", "x-token": "abc"},
        body=b"\x00\x01binary\xff",
        meta={"trapper": "my_trapper", "depth": 2},
        priority=5,
        callback="parse_detail",
        use_browser=True,
    )
    d = r.to_dict()
    r2 = Request.from_dict(d)

    assert r2.url == r.url
    assert r2.method == r.method
    assert r2.headers["content-type"] == "application/json"
    assert r2.headers["x-token"] == "abc"
    assert r2.body == b"\x00\x01binary\xff"
    assert r2.meta == {"trapper": "my_trapper", "depth": 2}
    assert r2.priority == 5
    assert r2.callback == "parse_detail"
    assert r2.use_browser is True


def test_to_dict_body_is_base64_string():
    r = Request(url="https://example.com", body=b"hello")
    d = r.to_dict()
    assert isinstance(d["body"], str)


def test_to_dict_no_body_is_none():
    r = Request(url="https://example.com")
    assert r.to_dict()["body"] is None


def test_from_dict_missing_optional_fields():
    r = Request.from_dict({"url": "https://example.com"})
    assert r.method == "GET"
    assert r.priority == 0
    assert r.use_browser is False
    assert r.body is None
    assert r.callback is None

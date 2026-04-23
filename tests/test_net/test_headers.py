from chaser.net.headers import Headers


def test_get_case_insensitive():
    h = Headers({"Content-Type": "text/html"})
    assert h["content-type"] == "text/html"
    assert h["CONTENT-TYPE"] == "text/html"
    assert h["Content-Type"] == "text/html"


def test_set_normalizes_key():
    h = Headers()
    h["X-Custom-Header"] = "value"
    assert "x-custom-header" in dict(h)


def test_contains_case_insensitive():
    h = Headers({"Authorization": "Bearer token"})
    assert "authorization" in h
    assert "AUTHORIZATION" in h
    assert "Authorization" in h


def test_get_with_default():
    h = Headers()
    assert h.get("missing") is None
    assert h.get("missing", "fallback") == "fallback"


def test_init_from_mapping():
    h = Headers({"A": "1", "B": "2"})
    assert h["a"] == "1"
    assert h["b"] == "2"


def test_init_from_kwargs():
    h = Headers(**{"Content-Type": "application/json"})
    assert h["content-type"] == "application/json"


def test_repr():
    h = Headers({"content-type": "text/plain"})
    assert "Headers" in repr(h)


def test_non_string_key_not_in():
    h = Headers({"x-key": "val"})
    assert 42 not in h

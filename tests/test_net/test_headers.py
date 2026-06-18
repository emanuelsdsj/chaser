import pytest

from chaser.net.headers import Headers

# --- construction ---


def test_init_from_str_mapping():
    h = Headers({"Content-Type": "text/html", "X-Foo": "bar"})
    assert h["content-type"] == "text/html"
    assert h["x-foo"] == "bar"


def test_init_from_list_mapping():
    h = Headers({"Set-Cookie": ["a=1", "b=2"]})
    assert h["set-cookie"] == "b=2"
    assert h.getlist("set-cookie") == ["a=1", "b=2"]


def test_init_from_mixed_mapping():
    h = Headers({"Content-Type": "text/html", "Set-Cookie": ["a=1", "b=2"]})
    assert h["content-type"] == "text/html"
    assert h.getlist("set-cookie") == ["a=1", "b=2"]


def test_init_from_kwargs():
    h = Headers(**{"Content-Type": "application/json"})
    assert h["content-type"] == "application/json"


def test_init_empty():
    h = Headers()
    assert len(h) == 0


# --- case insensitivity ---


def test_getitem_case_insensitive():
    h = Headers({"Content-Type": "text/html"})
    assert h["content-type"] == "text/html"
    assert h["CONTENT-TYPE"] == "text/html"
    assert h["Content-Type"] == "text/html"


def test_setitem_normalizes_key():
    h = Headers()
    h["X-Custom-Header"] = "value"
    assert "x-custom-header" in h
    assert "X-Custom-Header" in h


def test_contains_case_insensitive():
    h = Headers({"Authorization": "Bearer token"})
    assert "authorization" in h
    assert "AUTHORIZATION" in h
    assert "Authorization" in h


def test_non_string_key_not_in():
    h = Headers({"x-key": "val"})
    assert 42 not in h


# --- get / getlist ---


def test_get_returns_last_value():
    h = Headers({"set-cookie": ["a=1", "b=2", "c=3"]})
    assert h.get("set-cookie") == "c=3"


def test_get_with_default():
    h = Headers()
    assert h.get("missing") is None
    assert h.get("missing", "fallback") == "fallback"


def test_getlist_single_value():
    h = Headers({"content-type": "text/html"})
    assert h.getlist("content-type") == ["text/html"]


def test_getlist_multiple_values():
    h = Headers({"set-cookie": ["session=abc", "token=xyz"]})
    assert h.getlist("set-cookie") == ["session=abc", "token=xyz"]


def test_getlist_absent_key():
    h = Headers()
    assert h.getlist("set-cookie") == []


def test_getlist_case_insensitive():
    h = Headers({"Set-Cookie": ["a=1", "b=2"]})
    assert h.getlist("SET-COOKIE") == ["a=1", "b=2"]


def test_getlist_returns_copy():
    h = Headers({"set-cookie": ["a=1"]})
    lst = h.getlist("set-cookie")
    lst.append("mutated")
    assert h.getlist("set-cookie") == ["a=1"]


# --- setitem replaces ---


def test_setitem_replaces_all_values():
    h = Headers({"set-cookie": ["a=1", "b=2"]})
    h["set-cookie"] = "c=3"
    assert h.getlist("set-cookie") == ["c=3"]


# --- add ---


def test_add_appends_value():
    h = Headers({"set-cookie": "a=1"})
    h.add("set-cookie", "b=2")
    assert h.getlist("set-cookie") == ["a=1", "b=2"]


def test_add_creates_key_if_absent():
    h = Headers()
    h.add("set-cookie", "a=1")
    assert h.getlist("set-cookie") == ["a=1"]


def test_add_case_insensitive():
    h = Headers()
    h.add("Set-Cookie", "a=1")
    h.add("set-cookie", "b=2")
    assert h.getlist("set-cookie") == ["a=1", "b=2"]


# --- delete ---


def test_delitem():
    h = Headers({"content-type": "text/html", "x-foo": "bar"})
    del h["Content-Type"]
    assert "content-type" not in h
    assert "x-foo" in h


def test_delitem_missing_raises():
    h = Headers()
    with pytest.raises(KeyError):
        del h["missing"]


# --- mapping protocol ---


def test_len():
    h = Headers({"a": "1", "b": "2", "c": ["x", "y"]})
    assert len(h) == 3


def test_iter_yields_lowercase_keys_once():
    h = Headers({"Content-Type": "text/html", "Set-Cookie": ["a=1", "b=2"]})
    keys = list(h)
    assert sorted(keys) == ["content-type", "set-cookie"]


def test_dict_conversion_returns_last_values():
    h = Headers({"content-type": "text/html", "set-cookie": ["a=1", "b=2"]})
    d = dict(h)
    assert d == {"content-type": "text/html", "set-cookie": "b=2"}


def test_items_yields_last_values():
    h = Headers({"set-cookie": ["a=1", "b=2"]})
    assert list(h.items()) == [("set-cookie", "b=2")]


# --- to_dict_list ---


def test_to_dict_list_preserves_all():
    h = Headers({"content-type": "text/html", "set-cookie": ["a=1", "b=2"]})
    assert h.to_dict_list() == {"content-type": ["text/html"], "set-cookie": ["a=1", "b=2"]}


def test_to_dict_list_returns_copy():
    h = Headers({"set-cookie": ["a=1"]})
    d = h.to_dict_list()
    d["set-cookie"].append("mutated")
    assert h.getlist("set-cookie") == ["a=1"]


# --- repr ---


def test_repr():
    h = Headers({"content-type": "text/plain"})
    assert "Headers" in repr(h)

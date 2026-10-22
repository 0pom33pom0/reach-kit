import json
from contextlib import contextmanager
from unittest import mock

from reach import net


def response(body, status=200, ctype="text/html; charset=utf-8", url="https://example.com/"):
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
        ctype = "application/json"
    if isinstance(body, str):
        body = body.encode("utf-8")
    return net.Response(status, url, {"content-type": ctype}, body, False)


@contextmanager
def fake_http(routes):
    """routes: list of (substring, body_or_exception). First match wins. Records calls."""
    calls = []

    def fake(url, **kw):
        calls.append((url, kw))
        for needle, body in routes:
            if needle in url:
                if isinstance(body, Exception):
                    raise body
                return response(body, url=url)
        raise AssertionError(f"unexpected request: {url}")

    with mock.patch("reach.net.http_get", side_effect=fake):
        yield calls

"""Shared fixtures. No test may touch the network: sockets are blocked, and
HTTP goes through FakeWeb, a urllib handler that serves canned responses."""

import email.message
import io
import json
import socket
import urllib.request
import urllib.response

import pytest

import daily_post as d

ENV_VARS = (
    "AI_POST_PROVIDER",
    "AI_POST_SEARCH",
    "AI_POST_PROVIDER_TIMEOUT",
    "AI_POST_RSS_PER_FEED",
    "ANTHROPIC_API_KEY",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "OPENAI_COMPAT_BASE_URL",
    "OPENAI_COMPAT_MODEL",
    "OPENAI_COMPAT_API_KEY",
)

SENTINEL_KEY = "gsk_SENTINEL_do_not_print_0123456789abcdef"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Clean environment and a throwaway data directory for every test."""
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(d, "DATA_DIR", tmp_path)
    monkeypatch.setattr(d, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(d, "DRAFTS_FILE", tmp_path / "drafts.md")
    monkeypatch.setattr(d, "LOG_FILE", tmp_path / "run.log")
    monkeypatch.setattr(d, "ENV_FILE", tmp_path / "no.env")
    monkeypatch.setattr(d, "RUN_VIA", "")
    return tmp_path


class FakeWeb(urllib.request.HTTPSHandler):
    """Serves registered URLs; anything else fails the test.

    Responses travel through the real opener, so status codes and redirects
    are handled by urllib itself, including NoDowngradeRedirectHandler.
    """

    def __init__(self):
        super().__init__()
        self.routes = {}
        self.requests = []

    def add(self, url, body=b"", status=200, headers=None):
        """body may be bytes, a dict (sent as JSON) or an exception to raise."""
        self.routes[url] = (body, status, headers or {})

    def redirect(self, url, location, status=301):
        self.add(url, status=status, headers={"Location": location})

    def https_open(self, req):
        self.requests.append(req)
        if req.full_url not in self.routes:
            raise AssertionError(f"unexpected request to {req.full_url}")
        body, status, headers = self.routes[req.full_url]
        if isinstance(body, BaseException):
            raise body
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        msg = email.message.Message()
        for name, value in headers.items():
            msg[name] = value
        response = urllib.response.addinfourl(io.BytesIO(body), msg, req.full_url, status)
        response.msg = "fake"
        return response

    http_open = https_open  # for a local openai-compat base URL


@pytest.fixture
def web(monkeypatch):
    fake = FakeWeb()
    monkeypatch.setattr(
        d, "HTTP_OPENER", urllib.request.build_opener(fake, d.NoDowngradeRedirectHandler)
    )
    return fake


def completion(text):
    """An OpenAI-compatible chat completion response carrying `text`."""
    return {"choices": [{"index": 0, "message": {"role": "assistant", "content": text}}]}


MODEL_OUTPUT = """searched snippets the model saw first
===URL===
https://vendor.example/post
===TITLE===
A Real Release
===SOURCE===
Vendor
===TWEET===
Vendor shipped a thing that matters.
===LINKEDIN===
A longer take on why it matters.

What would you ask first?

#Tag
===WHY===
It is substantive.
===END===
"""


@pytest.fixture
def profile_file(tmp_path):
    path = tmp_path / "profile.md"
    path.write_text(
        "## Topics\n- Cloud\n- Security\n\n"
        "## Beat\nPractitioners.\n\n"
        "## Voice\nPlain.\n\n"
        "## Feeds\nNotes about feeds are ignored.\n"
        "- https://feeds.example/a.xml\n"
        "- https://feeds.example/b.xml\n"
    )
    return path

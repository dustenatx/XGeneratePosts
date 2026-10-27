"""No key in exit messages, logs, drafts or output. Provider errors map to
remedies (R12)."""

import json
import urllib.error

import pytest

import daily_post as d
from tests.conftest import MODEL_OUTPUT, SENTINEL_KEY, completion

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


@pytest.fixture
def groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", SENTINEL_KEY)
    return d.GroqProvider()


def error_body(message):
    return json.dumps({"error": {"message": message, "type": "invalid_request_error"}}).encode()


def test_key_is_sent_only_in_the_authorization_header(web, groq):
    web.add(GROQ_URL, completion(MODEL_OUTPUT))
    groq.generate("prompt", native_search=True)
    request = web.requests[0]
    assert request.get_header("Authorization") == f"Bearer {SENTINEL_KEY}"
    assert SENTINEL_KEY not in request.full_url
    assert SENTINEL_KEY.encode() not in request.data


def test_401_names_variable_and_redacts_echoed_key(web, groq):
    web.add(GROQ_URL, error_body(f"Invalid API Key {SENTINEL_KEY}"), status=401)
    with pytest.raises(SystemExit) as exc:
        groq.generate("prompt")
    assert "GROQ_API_KEY" in exc.value.code
    assert "https://console.groq.com/keys" in exc.value.code
    assert SENTINEL_KEY not in exc.value.code


def test_echoed_key_in_other_errors_is_redacted(web, groq):
    web.add(GROQ_URL, error_body(f"bad request for {SENTINEL_KEY}"), status=400)
    with pytest.raises(SystemExit) as exc:
        groq.generate("prompt")
    assert SENTINEL_KEY not in exc.value.code
    assert "[redacted]" in exc.value.code


def test_connection_error_is_redacted(web, groq):
    web.add(GROQ_URL, urllib.error.URLError(f"proxy said {SENTINEL_KEY}"))
    with pytest.raises(SystemExit) as exc:
        groq.generate("prompt")
    assert SENTINEL_KEY not in exc.value.code
    assert "Could not reach groq" in exc.value.code


def test_429_suggests_waiting_and_rss(web, groq):
    web.add(GROQ_URL, error_body("Rate limit reached"), status=429, headers={"retry-after": "7"})
    with pytest.raises(SystemExit) as exc:
        groq.generate("prompt")
    assert "waiting 7 seconds" in exc.value.code
    assert "--search rss" in exc.value.code


@pytest.mark.parametrize(
    ("status", "phrase"),
    [
        (403, "--search rss"),
        (404, "openai/gpt-oss-120b"),
        (413, "tokens-per-minute"),
        (503, "server error"),
    ],
)
def test_http_errors_map_to_remedies(web, groq, status, phrase):
    web.add(GROQ_URL, error_body("detail"), status=status)
    with pytest.raises(SystemExit) as exc:
        groq.generate("prompt")
    assert phrase in exc.value.code


def test_response_without_text_exits(web, groq):
    web.add(GROQ_URL, {"choices": []})
    with pytest.raises(SystemExit) as exc:
        groq.generate("prompt")
    assert "returned no text" in exc.value.code


def test_non_json_response_exits(web, groq):
    web.add(GROQ_URL, b"<html>login</html>")
    with pytest.raises(SystemExit) as exc:
        groq.generate("prompt")
    assert "not JSON" in exc.value.code


def test_redact_ignores_empty_and_short_values():
    assert d.redact("abc", "", "ab") == "abc"

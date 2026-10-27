"""R20: separate timeouts for feeds and for groq / openai-compat calls."""

import urllib.error

import pytest

from tests.conftest import MODEL_OUTPUT, SENTINEL_KEY, completion
from xgenerateposts import config, providers, search

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


@pytest.fixture
def groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", SENTINEL_KEY)
    return providers.GroqProvider()


def test_feed_requests_use_15_seconds(web):
    web.add("https://feeds.example/a.xml", b"<rss><channel/></rss>")
    search.fetch_feed("https://feeds.example/a.xml")
    assert web.requests[0].timeout == 15


def test_provider_calls_default_to_120_seconds(web, groq):
    web.add(GROQ_URL, completion(MODEL_OUTPUT))
    groq.generate("prompt", native_search=True)
    assert web.requests[0].timeout == 120


def test_provider_timeout_is_configurable(monkeypatch, web, groq):
    monkeypatch.setenv("AI_POST_PROVIDER_TIMEOUT", "30")
    web.add(GROQ_URL, completion(MODEL_OUTPUT))
    groq.generate("prompt")
    assert web.requests[0].timeout == 30


@pytest.mark.parametrize("value", ["0", "-5", "soon", "nan", "inf"])
def test_bad_provider_timeout_exits(monkeypatch, value):
    monkeypatch.setenv("AI_POST_PROVIDER_TIMEOUT", value)
    with pytest.raises(SystemExit) as exc:
        config.provider_timeout()
    assert "AI_POST_PROVIDER_TIMEOUT" in exc.value.code


@pytest.mark.parametrize("error", [TimeoutError(), urllib.error.URLError(TimeoutError())])
def test_provider_timeout_exits_with_remedy(web, groq, error):
    web.add(GROQ_URL, error)
    with pytest.raises(SystemExit) as exc:
        groq.generate("prompt", native_search=True)
    assert "no response within 120 seconds" in exc.value.code
    assert "AI_POST_PROVIDER_TIMEOUT" in exc.value.code

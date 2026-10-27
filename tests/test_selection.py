"""R1, R3, R4, R6: provider and search-source selection."""

import pytest

import daily_post as d


def test_provider_defaults_to_groq():
    assert d.select_provider(None) == "groq"


def test_provider_env_beats_default(monkeypatch):
    monkeypatch.setenv("AI_POST_PROVIDER", "Anthropic")
    assert d.select_provider(None) == "anthropic"


def test_provider_flag_beats_env(monkeypatch):
    monkeypatch.setenv("AI_POST_PROVIDER", "anthropic")
    assert d.select_provider("openai-compat") == "openai-compat"


def test_unknown_provider_from_env_exits(monkeypatch):
    monkeypatch.setenv("AI_POST_PROVIDER", "gemini")
    with pytest.raises(SystemExit) as exc:
        d.select_provider(None)
    assert "AI_POST_PROVIDER" in exc.value.code


def test_groq_model_default_and_override(monkeypatch):
    assert d.GroqProvider().model == "openai/gpt-oss-120b"
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    assert d.GroqProvider().model == "openai/gpt-oss-20b"


@pytest.mark.parametrize(
    ("provider", "expected"),
    [("anthropic", "native"), ("groq", "native"), ("openai-compat", "rss")],
)
def test_search_defaults_by_provider(provider, expected):
    assert d.select_search(None, provider) == expected


def test_search_env_beats_provider_default(monkeypatch):
    monkeypatch.setenv("AI_POST_SEARCH", "rss")
    assert d.select_search(None, "groq") == "rss"


def test_search_flag_beats_env(monkeypatch):
    monkeypatch.setenv("AI_POST_SEARCH", "rss")
    assert d.select_search("native", "groq") == "native"


def test_native_search_refused_for_openai_compat():
    with pytest.raises(SystemExit) as exc:
        d.select_search("native", "openai-compat")
    assert "--search rss" in exc.value.code


def test_unknown_search_from_env_exits(monkeypatch):
    monkeypatch.setenv("AI_POST_SEARCH", "bing")
    with pytest.raises(SystemExit):
        d.select_search(None, "groq")


def test_missing_groq_key_names_variable_and_url():
    with pytest.raises(SystemExit) as exc:
        d.GroqProvider().require_credentials()
    assert "--provider groq" in exc.value.code
    assert "GROQ_API_KEY" in exc.value.code
    assert "https://console.groq.com/keys" in exc.value.code


def test_missing_anthropic_key_names_variable_and_url():
    with pytest.raises(SystemExit) as exc:
        d.AnthropicProvider().require_credentials()
    assert "ANTHROPIC_API_KEY" in exc.value.code
    assert d.CONSOLE_KEYS in exc.value.code


def test_openai_compat_needs_base_url_and_model():
    with pytest.raises(SystemExit) as exc:
        d.OpenAICompatProvider().require_credentials()
    assert "OPENAI_COMPAT_BASE_URL and OPENAI_COMPAT_MODEL" in exc.value.code


def test_openai_compat_refuses_plain_http_to_remote_host(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPAT_BASE_URL", "http://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPAT_MODEL", "m")
    with pytest.raises(SystemExit) as exc:
        d.OpenAICompatProvider().require_credentials()
    assert "https://" in exc.value.code


def test_openai_compat_allows_local_ollama_without_key(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPAT_BASE_URL", "http://localhost:11434/v1/")
    monkeypatch.setenv("OPENAI_COMPAT_MODEL", "llama3")
    provider = d.OpenAICompatProvider()
    provider.require_credentials()
    assert provider.base_url == "http://localhost:11434/v1"


def test_groq_request_has_browser_search_only_for_native():
    provider = d.GroqProvider()
    native = provider.request_body("p", native_search=True)
    assert native["tools"] == [{"type": "browser_search"}]
    assert native["tool_choice"] == "required"
    assert native["reasoning_effort"] == "low"
    assert "tools" not in provider.request_body("p", native_search=False)


def test_importing_the_script_does_not_load_anthropic():
    import sys

    assert "anthropic" not in sys.modules

"""R17: dedup by URL or normalized title."""

import pytest

import daily_post as d
from tests.conftest import MODEL_OUTPUT


class CannedProvider:
    name = "canned"
    model = "m"

    def __init__(self, text):
        self.text = text
        self.prompts = []

    def generate(self, prompt, native_search=True):
        self.prompts.append(prompt)
        return self.text


PROFILE = {"beat": "b", "voice": "v"}


def test_normalize_title_casefolds_and_collapses_whitespace():
    assert d.normalize_title("  A  Real\tRELEASE\n") == "a real release"


def test_title_match_with_different_url_is_rejected():
    history_titles = ["a real   release"]
    with pytest.raises(SystemExit) as exc:
        d.generate_item(
            CannedProvider(MODEL_OUTPUT),
            d.NativeSearch(),
            PROFILE,
            "topic",
            ["https://other.example/same-story"],
            history_titles,
        )
    assert "already covered" in exc.value.code


def test_url_match_is_rejected():
    with pytest.raises(SystemExit):
        d.generate_item(
            CannedProvider(MODEL_OUTPUT),
            d.NativeSearch(),
            PROFILE,
            "topic",
            ["https://vendor.example/post"],
            [],
        )


def test_new_item_passes_and_prompt_lists_used_urls_and_titles():
    provider = CannedProvider(MODEL_OUTPUT)
    item = d.generate_item(
        provider, d.NativeSearch(), PROFILE, "topic", ["https://old.example/1"], ["Old Story"]
    )
    assert item["url"] == "https://vendor.example/post"
    assert "- https://old.example/1" in provider.prompts[0]
    assert "- Old Story" in provider.prompts[0]


def test_used_from_reads_history():
    history = [
        {"url": "https://a", "title": "A"},
        {"url": "https://b", "title": "B", "topic": "t"},
    ]
    assert d.used_from(history) == (["https://a", "https://b"], ["A", "B"])

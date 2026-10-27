import pytest

import daily_post as d

TOPICS = ["Cloud infrastructure", "Cloud cost", "Security"]


def test_menu_strips_bullets_and_numbers():
    profile = {"topics": "- One\n* Two\n3. Three\n4) Four\n# comment\n\n"}
    assert d.topic_menu(profile) == ["One", "Two", "Three", "Four"]


def test_menu_falls_back_to_catalog():
    assert d.topic_menu({}) == d.TOPIC_CATALOG


def test_number_selects_entry():
    assert d.choose_topic(TOPICS, "3") == "Security"


def test_unique_substring_selects_entry():
    assert d.choose_topic(TOPICS, "secur") == "Security"


def test_ambiguous_substring_exits():
    with pytest.raises(SystemExit) as exc:
        d.choose_topic(TOPICS, "cloud")
    assert "Ambiguous" in exc.value.code


def test_free_text_passes_through():
    assert d.choose_topic(TOPICS, "Quantum networking") == "Quantum networking"


def test_out_of_range_number_is_free_text():
    assert d.choose_topic(TOPICS, "9") == "9"


def test_random_picks_from_menu():
    assert d.choose_topic(TOPICS, pick_random=True) in TOPICS


def test_no_terminal_and_no_topic_exits(monkeypatch):
    monkeypatch.setattr(d.sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit) as exc:
        d.choose_topic(TOPICS)
    assert "--random-topic" in exc.value.code

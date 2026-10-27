"""R22: RSS candidates ranked by topic words, then capped in total."""

from datetime import UTC, datetime

import pytest

from tests.test_rss import FEED_A, FEED_B, PROFILE, dated, rss
from xgenerateposts import config, feeds, search


def entry(title, day=None, summary=""):
    when = datetime(2026, 10, day, 8, tzinfo=UTC) if day else None
    return {"title": title, "link": f"https://x.example/{title}", "date": when, "summary": summary}


def titles(entries):
    return [e["title"] for e in entries]


def block_titles(block):
    return [line.split("Title: ")[1] for line in block.splitlines() if "Title: " in line]


def test_more_topic_words_rank_first():
    entries = [
        entry("Nothing relevant", 20),
        entry("Kubernetes release", 10),
        entry("Kubernetes security release", 5),
    ]
    assert titles(feeds.ranked(entries, "Kubernetes security", 20)) == [
        "Kubernetes security release",
        "Kubernetes release",
        "Nothing relevant",
    ]


def test_summary_counts_and_case_is_ignored():
    entries = [entry("Plain", 1, summary="All about KUBERNETES"), entry("Other", 2)]
    assert titles(feeds.ranked(entries, "kubernetes", 20)) == ["Plain", "Other"]


def test_ties_break_newest_first_and_undated_go_last():
    entries = [
        entry("undated one"),
        entry("old", 1),
        entry("undated two"),
        entry("new", 9),
        entry("mid", 5),
    ]
    assert titles(feeds.ranked(entries, "", 20)) == [
        "new",
        "mid",
        "old",
        "undated one",
        "undated two",
    ]


def test_ties_within_a_score_break_by_date():
    entries = [entry("cloud old", 1), entry("other", 30), entry("cloud new", 9)]
    assert titles(feeds.ranked(entries, "Cloud", 20)) == ["cloud new", "cloud old", "other"]


def test_each_distinct_word_counts_once():
    entries = [entry("cloud cloud cloud", 9), entry("cloud costs", 1)]
    assert titles(feeds.ranked(entries, "cloud costs", 20)) == ["cloud costs", "cloud cloud cloud"]


def test_words_are_whole_not_substrings():
    """'cloudy' does not count as 'cloud'."""
    entries = [entry("cloudy weather", 9), entry("cloud news", 1)]
    assert titles(feeds.ranked(entries, "cloud", 20)) == ["cloud news", "cloudy weather"]


def test_stop_words_and_short_words_are_removed():
    assert feeds.words("AI and the Cloud: Tools for ML with Kubernetes") == {
        "cloud",
        "tools",
        "kubernetes",
    }


def test_stop_words_do_not_score():
    entries = [entry("the and for with", 9), entry("security", 1)]
    assert titles(feeds.ranked(entries, "Security for the cloud", 20)) == [
        "security",
        "the and for with",
    ]


def test_ranked_keeps_at_most_limit():
    entries = [entry(f"e{n}", n) for n in range(1, 10)]
    assert titles(feeds.ranked(entries, "", 3)) == ["e9", "e8", "e7"]


def test_default_total_cap_is_20():
    assert config.rss_max_entries() == 20


def test_total_cap_applies_after_per_feed_cap(monkeypatch, web):
    monkeypatch.setenv("AI_POST_RSS_MAX_ENTRIES", "4")
    web.add(FEED_A, rss(*[(f"A{n}", f"https://a.example/{n}", dated(n)) for n in range(10, 15)]))
    web.add(
        FEED_B,
        rss(
            ("Kubernetes B1", "https://b.example/1", dated(1)),
            ("Kubernetes B2", "https://b.example/2", dated(2)),
            ("B3", "https://b.example/3", dated(3)),
            ("B4", "https://b.example/4", dated(4)),
            ("Kubernetes B5", "https://b.example/5", dated(5)),
        ),
    )
    rss_search = search.RssSearch(PROFILE)
    block = rss_search.candidates([], [], "Kubernetes")
    # Per feed (3 newest): A14 A13 A12 and B5 B4 B3. Only B5 of those has the
    # topic word; B1 and B2 were already cut by the per-feed cap.
    assert block_titles(block) == ["Kubernetes B5", "A14", "A13", "A12"]
    assert rss_search.links == {
        "https://b.example/5",
        "https://a.example/14",
        "https://a.example/13",
        "https://a.example/12",
    }


@pytest.mark.parametrize("value", ["0", "-1", "abc", "2.5"])
def test_bad_total_cap_exits(monkeypatch, value):
    monkeypatch.setenv("AI_POST_RSS_MAX_ENTRIES", value)
    with pytest.raises(SystemExit) as exc:
        config.rss_max_entries()
    assert "AI_POST_RSS_MAX_ENTRIES must be a whole number of 1 or more" in exc.value.code


def test_bad_total_cap_exits_before_fetching(monkeypatch, web):
    monkeypatch.setenv("AI_POST_RSS_MAX_ENTRIES", "0")
    with pytest.raises(SystemExit):
        search.RssSearch(PROFILE)
    assert web.requests == []

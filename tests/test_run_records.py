"""R13 and end-to-end runs of main() against canned HTTP: which provider and
search source produced each run, and no key anywhere in the output."""

import json

import pytest

import daily_post as d
from tests.conftest import MODEL_OUTPUT, SENTINEL_KEY, completion

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
FEED = rb"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>A Real Release</title><link>https://vendor.example/post</link>
<pubDate>Sat, 25 Oct 2026 10:00:00 GMT</pubDate><description>News.</description></item>
</channel></rss>"""


def run_main(monkeypatch, *args):
    monkeypatch.setattr(d.sys, "argv", ["daily_post.py", *args])
    d.main()


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", SENTINEL_KEY)


def everything_written(isolated, capsys):
    out = capsys.readouterr()
    files = "".join(p.read_text() for p in isolated.iterdir() if p.is_file())
    return out.out + out.err + files


def test_groq_native_run_records_provider_and_search(
    monkeypatch, web, keyed, isolated, profile_file, capsys
):
    web.add(GROQ_URL, completion(MODEL_OUTPUT))
    run_main(monkeypatch, "--provider", "groq", "--topic", "Cloud", "--profile", str(profile_file))

    body = json.loads(web.requests[0].data)
    assert body["tools"] == [{"type": "browser_search"}]

    entry = json.loads((isolated / "history.json").read_text())[-1]
    assert entry["provider"] == "groq"
    assert entry["model"] == "openai/gpt-oss-120b"
    assert entry["search"] == "native"
    assert "Via: groq/openai/gpt-oss-120b, search native" in (isolated / "drafts.md").read_text()
    assert "[via groq/openai/gpt-oss-120b, search native]" in (isolated / "run.log").read_text()
    assert SENTINEL_KEY not in everything_written(isolated, capsys)


def test_groq_rss_run_sends_feed_block_and_no_search_tool(
    monkeypatch, web, keyed, isolated, profile_file, capsys
):
    web.add("https://feeds.example/a.xml", FEED)
    web.add("https://feeds.example/b.xml", b"x", status=503)
    web.add(GROQ_URL, completion(MODEL_OUTPUT))
    run_main(
        monkeypatch,
        "--provider",
        "groq",
        "--search",
        "rss",
        "--topic",
        "Cloud",
        "--profile",
        str(profile_file),
    )

    body = json.loads(web.requests[-1].data)
    assert "tools" not in body
    prompt = body["messages"][0]["content"]
    assert "<feed_entries>" in prompt
    assert "Link: https://vendor.example/post" in prompt

    entry = json.loads((isolated / "history.json").read_text())[-1]
    assert entry["search"] == "rss"
    assert SENTINEL_KEY not in everything_written(isolated, capsys)


def test_missing_key_exits_before_any_request(monkeypatch, web, profile_file):
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch, "--topic", "Cloud", "--profile", str(profile_file))
    assert "GROQ_API_KEY" in exc.value.code
    assert web.requests == []


def test_history_entries_without_new_keys_still_list(monkeypatch, isolated, capsys):
    (isolated / "history.json").write_text(
        json.dumps([{"date": "2026-08-17", "url": "https://old.example", "title": "Old"}])
    )
    run_main(monkeypatch, "--history")
    assert "https://old.example" in capsys.readouterr().out

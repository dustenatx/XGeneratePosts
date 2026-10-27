"""Acceptance tests for draft parsing, history, deduplication, and secrets."""

from __future__ import annotations

import json


def history_entry(url: str, title: str) -> dict[str, str]:
    """Build a minimal history entry using the documented schema."""
    return {
        "date": "2026-10-20",
        "url": url,
        "title": title,
        "topic": "Security",
    }


def test_r11_draft_only_default_parses_delimited_output(
    run_cli,
    model_stub,
    successful_rss_environment,
    model_text,
    data_dir,
) -> None:
    """R11: the delimited response becomes drafts without an explicit posting flag."""
    result = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(),
    )

    assert result.returncode == 0, f"Valid delimited output must succeed: {result.stderr}"
    assert "A useful security engineering development worth watching." in result.stdout, (
        "Parsed X draft must be printed"
    )
    assert (
        "A useful security engineering development, with context for practitioners."
        in result.stdout
    ), "Parsed LinkedIn draft must be printed"
    assert (data_dir / "drafts.md").is_file(), "Successful run must write drafts.md"
    history = json.loads((data_dir / "history.json").read_text(encoding="utf-8"))
    assert history, "Successful draft-only run must add a history entry"


def test_r11_x_draft_is_trimmed_to_at_most_255_characters(
    run_cli,
    model_stub,
    successful_rss_environment,
) -> None:
    """R11: an over-length X draft is trimmed to no more than 255 characters."""
    long_tweet = "X acceptance marker " + ("x" * 500)
    content = (
        "===URL===\nhttps://example.test/long-x\n"
        "===TITLE===\nLong X test\n"
        "===SOURCE===\nhttps://example.test/feed.xml\n"
        f"===TWEET===\n{long_tweet}\n"
        "===LINKEDIN===\nA LinkedIn draft.\n"
        "===WHY===\nTesting X trimming.\n"
        "===END===\n"
    )
    model_stub.state.body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()

    result = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(),
    )

    assert result.returncode == 0, f"Long X draft must be handled: {result.stderr}"
    drafts = result.stdout
    x_start = drafts.find("X acceptance marker")
    assert x_start >= 0, "Trimmed X draft must be present in output"
    x_end = drafts.find("\n", x_start)
    x_draft = drafts[x_start:] if x_end < 0 else drafts[x_start:x_end]
    assert len(x_draft) <= 255, f"X draft must contain at most 255 characters, got {len(x_draft)}"


def test_r11_overlength_linkedin_is_kept_and_warned(
    run_cli,
    model_stub,
    successful_rss_environment,
) -> None:
    """R11: LinkedIn text over 1,100 characters is retained with a length warning."""
    linkedin = "LinkedIn acceptance marker " + ("L" * 1200)
    content = (
        "===URL===\nhttps://example.test/long-linkedin\n"
        "===TITLE===\nLong LinkedIn test\n"
        "===SOURCE===\nhttps://example.test/feed.xml\n"
        "===TWEET===\nA short X draft.\n"
        f"===LINKEDIN===\n{linkedin}\n"
        "===WHY===\nTesting LinkedIn warning.\n"
        "===END===\n"
    )
    model_stub.state.body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()

    result = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(),
    )

    assert result.returncode == 0, f"Over-length LinkedIn draft must be retained: {result.stderr}"
    assert linkedin in result.stdout, "Over-length LinkedIn draft must remain untruncated"
    assert "1100" in result.stderr, (
        "Warning on standard error must state the 1,100-character ceiling"
    )
    assert str(len(linkedin)) in result.stderr, (
        "Warning on standard error must state the draft's character length"
    )


def test_r11_draft_only_does_not_send_publish_request(
    run_cli,
    model_stub,
    successful_rss_environment,
) -> None:
    """R11: neither social platform is published without a posting flag."""
    result = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(),
    )

    assert result.returncode == 0, f"Draft-only run must succeed: {result.stderr}"
    assert len(model_stub.state.snapshot()) == 1, "Draft-only run must make only its model request"
    assert all(
        request["path"] == "/v1/chat/completions" for request in model_stub.state.snapshot()
    ), "No publishing request may be made in draft-only mode"


def test_r13_provider_and_search_source_are_persisted(
    run_cli,
    model_stub,
    successful_rss_environment,
    data_dir,
) -> None:
    """R13: all three persistent files identify the provider and search source."""
    result = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(),
    )

    assert result.returncode == 0, f"Successful run required: {result.stderr}"
    log = (data_dir / "run.log").read_text(encoding="utf-8").lower()
    drafts = (data_dir / "drafts.md").read_text(encoding="utf-8").lower()
    history = json.loads((data_dir / "history.json").read_text(encoding="utf-8"))

    assert "openai-compat" in log, "run.log must record the provider"
    assert "rss" in log, "run.log must record the search source"
    assert "openai-compat" in drafts, "drafts.md must record the provider"
    assert "rss" in drafts, "drafts.md must record the search source"
    assert history, "history.json must contain the successful run"

    latest = history[-1]
    for key in ("date", "url", "title", "topic", "provider", "model", "search"):
        assert key in latest, f"History entry must include {key}"

    assert latest["provider"] == "openai-compat", "History must identify the selected provider"
    assert latest["model"] == "test-model", "History must identify the model"
    assert latest["search"] == "rss", "History must identify the search source"


def test_r17_used_url_is_not_selected_again(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    rss_feed,
    env_builder,
    data_dir,
) -> None:
    """R17: a candidate with a URL already in history is rejected."""
    duplicate = {
        "title": "Previously used URL candidate",
        "link": "https://example.test/used-url",
        "date": "Mon, 26 Oct 2026 08:00:00 +0000",
        "summary": "Duplicate URL summary marker.",
    }
    fresh = {
        "title": "Fresh candidate marker",
        "link": "https://example.test/fresh-url",
        "date": "Mon, 26 Oct 2026 09:00:00 +0000",
        "summary": "Fresh candidate summary.",
    }
    feed_stub.set_response("/feed.xml", rss_feed([duplicate, fresh]))
    profile_writer(feeds=[feed_stub.url()])
    certificate, _ = tls_certificate

    (data_dir / "history.json").write_text(
        json.dumps([history_entry(duplicate["link"], duplicate["title"])]),
        encoding="utf-8",
    )

    result = run_cli(
        "--provider",
        "openai-compat",
        "--search",
        "rss",
        env=env_builder(
            OPENAI_COMPAT_BASE_URL=model_stub.base_url,
            OPENAI_COMPAT_MODEL="test-model",
            SSL_CERT_FILE=str(certificate),
        ),
    )
    prompt = json.dumps(model_stub.state.snapshot(), ensure_ascii=False)

    assert result.returncode == 0, f"Fresh candidate run must succeed: {result.stderr}"
    assert "Fresh candidate marker" in prompt, "Fresh candidate must reach the model"
    assert "Duplicate URL summary marker" not in prompt, (
        "Candidate with an already-used URL must be excluded"
    )


def test_r17_normalized_title_match_with_different_url_is_rejected(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    rss_feed,
    env_builder,
    data_dir,
) -> None:
    """R17: case-folded, whitespace-collapsed title duplicates are rejected."""
    duplicate = {
        "title": "  SAME   security STORY ",
        "link": "https://example.test/different-url",
        "date": "Mon, 26 Oct 2026 08:00:00 +0000",
        "summary": "Normalized title duplicate summary marker.",
    }
    fresh = {
        "title": "Distinct fresh candidate",
        "link": "https://example.test/distinct",
        "date": "Mon, 26 Oct 2026 09:00:00 +0000",
        "summary": "Distinct candidate summary.",
    }
    feed_stub.set_response("/feed.xml", rss_feed([duplicate, fresh]))
    profile_writer(feeds=[feed_stub.url()])
    certificate, _ = tls_certificate

    (data_dir / "history.json").write_text(
        json.dumps(
            [
                history_entry(
                    "https://example.test/old-url",
                    "same security story",
                )
            ]
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "--provider",
        "openai-compat",
        "--search",
        "rss",
        env=env_builder(
            OPENAI_COMPAT_BASE_URL=model_stub.base_url,
            OPENAI_COMPAT_MODEL="test-model",
            SSL_CERT_FILE=str(certificate),
        ),
    )
    prompt = json.dumps(model_stub.state.snapshot(), ensure_ascii=False)

    assert result.returncode == 0, f"Fresh candidate run must succeed: {result.stderr}"
    assert "Distinct fresh candidate" in prompt, "Fresh candidate must reach the model"
    assert "Normalized title duplicate summary marker" not in prompt, (
        "Normalized title match must be rejected despite a different URL"
    )


def test_r17_used_titles_are_passed_to_model_prompt(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    rss_feed,
    env_builder,
    data_dir,
) -> None:
    """R17: used titles are included in the prompt."""
    used_title = "Previously published title sentinel"
    fresh = {
        "title": "Current fresh feed item",
        "link": "https://example.test/current",
        "date": "Mon, 26 Oct 2026 09:00:00 +0000",
        "summary": "Current feed summary.",
    }
    feed_stub.set_response("/feed.xml", rss_feed([fresh]))
    profile_writer(feeds=[feed_stub.url()])
    certificate, _ = tls_certificate

    (data_dir / "history.json").write_text(
        json.dumps(
            [
                history_entry(
                    "https://example.test/old",
                    used_title,
                )
            ]
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "--provider",
        "openai-compat",
        "--search",
        "rss",
        env=env_builder(
            OPENAI_COMPAT_BASE_URL=model_stub.base_url,
            OPENAI_COMPAT_MODEL="test-model",
            SSL_CERT_FILE=str(certificate),
        ),
    )
    prompt = json.dumps(model_stub.state.snapshot(), ensure_ascii=False)

    assert result.returncode == 0, f"Run must succeed: {result.stderr}"
    assert used_title in prompt, "Used title must be passed into the model prompt"


def test_secrets_do_not_leak_on_success_or_failure(
    run_cli,
    model_stub,
    successful_rss_environment,
    data_dir,
) -> None:
    """Definition of done 4: API key sentinel never leaks to output or persistent files."""
    sentinel = "acceptance-secret-sentinel-8f34c1"

    success = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(OPENAI_COMPAT_API_KEY=sentinel),
    )
    assert success.returncode == 0, f"Success path must work: {success.stderr}"

    model_stub.state.status = 500
    model_stub.state.body = b'{"error":"simulated provider failure"}'

    failure = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(OPENAI_COMPAT_API_KEY=sentinel),
    )
    assert failure.returncode != 0, "Provider error path must fail"

    observed = success.stdout + success.stderr + failure.stdout + failure.stderr
    for filename in ("run.log", "drafts.md", "history.json"):
        path = data_dir / filename
        if path.exists():
            observed += path.read_text(encoding="utf-8")

    assert sentinel not in observed, (
        "API key must not appear in output or persistent data on either path"
    )
    assert failure.log_lines_added == 1, (
        "Expected provider failure must add exactly one run.log line"
    )

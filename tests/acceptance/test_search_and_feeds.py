"""Search-source selection, feed handling, and feed security acceptance tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime, parsedate_to_datetime


def make_entry(title: str, url: str, days_ago: int = 0) -> dict[str, str]:
    """Return a dated feed entry."""
    published = datetime.now(UTC) - timedelta(days=days_ago)
    return {
        "title": title,
        "link": url,
        "date": format_datetime(published),
        "summary": f"Summary for {title}",
    }


def test_r6_search_flag_overrides_environment(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    rss_feed,
    env_builder,
) -> None:
    """R6: --search overrides AI_POST_SEARCH."""
    entry = make_entry(
        "Flag-selected RSS marker",
        "https://example.test/flag-selected",
    )
    feed_stub.set_response("/feed.xml", rss_feed([entry]))
    profile_writer(feeds=[feed_stub.url()])
    certificate, _ = tls_certificate

    result = run_cli(
        "--provider",
        "openai-compat",
        "--search",
        "rss",
        env=env_builder(
            AI_POST_SEARCH="native",
            OPENAI_COMPAT_BASE_URL=model_stub.base_url,
            OPENAI_COMPAT_MODEL="test-model",
            SSL_CERT_FILE=str(certificate),
        ),
    )

    assert result.returncode == 0, f"Flag-selected RSS must succeed: {result.stderr}"
    assert "Flag-selected RSS marker" in json.dumps(model_stub.state.snapshot()), (
        "RSS selected by the flag must reach the model prompt"
    )


def test_r6_search_environment_overrides_provider_default(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    rss_feed,
    env_builder,
) -> None:
    """R6: AI_POST_SEARCH overrides the provider-specific default."""
    entry = make_entry(
        "Environment-selected RSS marker",
        "https://example.test/environment-selected",
    )
    feed_stub.set_response("/feed.xml", rss_feed([entry]))
    profile_writer(feeds=[feed_stub.url()])
    certificate, _ = tls_certificate

    result = run_cli(
        "--provider",
        "openai-compat",
        env=env_builder(
            AI_POST_SEARCH="rss",
            OPENAI_COMPAT_BASE_URL=model_stub.base_url,
            OPENAI_COMPAT_MODEL="test-model",
            SSL_CERT_FILE=str(certificate),
        ),
    )

    assert result.returncode == 0, f"Environment-selected RSS must succeed: {result.stderr}"
    assert "Environment-selected RSS marker" in json.dumps(model_stub.state.snapshot()), (
        "RSS selected through the environment must reach the model prompt"
    )


def test_r6_openai_compat_defaults_to_rss(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    rss_feed,
    env_builder,
) -> None:
    """R6: OpenAI-compatible provider defaults to RSS when no search setting exists."""
    entry = make_entry(
        "Default RSS marker",
        "https://example.test/default-rss",
    )
    feed_stub.set_response("/feed.xml", rss_feed([entry]))
    profile_writer(feeds=[feed_stub.url()])
    certificate, _ = tls_certificate

    result = run_cli(
        "--provider",
        "openai-compat",
        env=env_builder(
            OPENAI_COMPAT_BASE_URL=model_stub.base_url,
            OPENAI_COMPAT_MODEL="test-model",
            SSL_CERT_FILE=str(certificate),
        ),
    )

    assert result.returncode == 0, f"Default RSS run must succeed: {result.stderr}"
    assert "Default RSS marker" in json.dumps(model_stub.state.snapshot()), (
        "Default RSS entries must reach the model prompt"
    )


def test_r8_feed_title_link_date_summary_reach_prompt(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    rss_feed,
    env_builder,
) -> None:
    """R8: RSS title, link, date, and summary are passed to the model."""
    entry = make_entry(
        "All-fields acceptance marker",
        "https://example.test/all-fields",
    )
    feed_stub.set_response("/feed.xml", rss_feed([entry]))
    profile_writer(feeds=[feed_stub.url()])
    certificate, _ = tls_certificate

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

    assert result.returncode == 0, f"RSS feed must succeed: {result.stderr}"
    prompt = json.dumps(model_stub.state.snapshot(), ensure_ascii=False)

    calendar_date = parsedate_to_datetime(entry["date"]).date().isoformat()
    for value in (
        entry["title"],
        entry["link"],
        calendar_date,
        entry["summary"],
    ):
        assert value in prompt, f"Feed field must reach the model prompt: {value}"


def test_r8_atom_feed_is_supported(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    atom_feed,
    env_builder,
) -> None:
    """R8: an Atom feed yields candidate entries."""
    entry = make_entry(
        "Atom feed acceptance marker",
        "https://example.test/atom-entry",
    )
    feed_stub.set_response(
        "/atom.xml",
        atom_feed([entry]),
        headers={"Content-Type": "application/atom+xml"},
    )
    profile_writer(feeds=[feed_stub.url("/atom.xml")])
    certificate, _ = tls_certificate

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

    assert result.returncode == 0, f"Atom feed must succeed: {result.stderr}"
    prompt = json.dumps(model_stub.state.snapshot())
    assert "Atom feed acceptance marker" in prompt, "Atom candidate must reach the model prompt"
    calendar_date = parsedate_to_datetime(entry["date"]).date().isoformat()
    assert calendar_date in prompt, "R8: the Atom entry date must reach the prompt as YYYY-MM-DD"


def test_r9_missing_feeds_section_fails_with_guidance(
    run_cli,
    model_stub,
    profile_writer,
    env_builder,
    data_dir,
) -> None:
    """R9: RSS without a Feeds section fails with instructions."""
    profile_writer(include_feeds_section=False)
    result = run_cli(
        "--provider",
        "openai-compat",
        "--search",
        "rss",
        env=env_builder(
            OPENAI_COMPAT_BASE_URL=model_stub.base_url,
            OPENAI_COMPAT_MODEL="test-model",
        ),
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, "Missing Feeds section must fail"
    assert "feed" in output.lower(), "Failure must explain feed configuration"
    assert "Traceback (most recent call last)" not in output, (
        "Expected missing-feeds failure must not print a traceback"
    )
    assert not model_stub.state.snapshot(), (
        "Missing Feeds section must fail before contacting the model"
    )
    assert result.log_lines_added == 1, (
        "Expected missing-feeds failure must add exactly one run.log line"
    )


def test_r10_one_failed_feed_is_logged_and_skipped(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    rss_feed,
    env_builder,
    data_dir,
) -> None:
    """R10: one failed feed is logged while a successful feed is processed."""
    entry = make_entry(
        "Surviving feed acceptance marker",
        "https://example.test/surviving-feed",
    )
    feed_stub.set_response("/broken.xml", b"temporary failure", status=503)
    feed_stub.set_response("/good.xml", rss_feed([entry]))
    profile_writer(feeds=[feed_stub.url("/broken.xml"), feed_stub.url("/good.xml")])
    certificate, _ = tls_certificate

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

    assert result.returncode == 0, f"Remaining successful feed must be used: {result.stderr}"
    assert "Surviving feed acceptance marker" in json.dumps(model_stub.state.snapshot()), (
        "Successful feed entry must reach the model"
    )
    log = (data_dir / "run.log").read_text(encoding="utf-8")
    assert "/broken.xml" in log, "Failed feed must be logged"


def test_r10_all_feeds_failing_is_expected_failure(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    env_builder,
    data_dir,
) -> None:
    """R10: all failed feeds cause a clean, logged failure."""
    feed_stub.set_response("/broken.xml", b"temporary failure", status=503)
    profile_writer(feeds=[feed_stub.url("/broken.xml")])
    certificate, _ = tls_certificate

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
    output = result.stdout + result.stderr

    assert result.returncode != 0, "All-feed failure must exit nonzero"
    assert "Traceback (most recent call last)" not in output, (
        "Expected all-feed failure must not print a traceback"
    )
    assert "/broken.xml" in (data_dir / "run.log").read_text(encoding="utf-8"), (
        "Failed feed must be logged"
    )
    assert not model_stub.state.snapshot(), "Model must not be called when every feed fails"
    assert result.log_lines_added == 2, (
        "Section 11: one skipped-feed line for the one feed, plus exactly one failure line"
    )


def test_r18_https_to_http_redirect_is_refused_and_skipped(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    rss_feed,
    env_builder,
    data_dir,
) -> None:
    """R18: HTTPS-to-HTTP redirect is refused, logged, and skipped."""
    # The plain-HTTP target is live and serves a valid feed, so following the
    # redirect would succeed and the downgraded entry would reach the prompt.
    downgraded = make_entry(
        "Downgraded feed marker must not appear",
        "https://example.test/downgraded",
    )
    model_stub.state.plain_http_feed = rss_feed([downgraded]).encode()
    http_root = model_stub.base_url.removesuffix("/v1")
    feed_stub.redirect_to_http("/redirect.xml", f"{http_root}/untrusted.xml")
    entry = make_entry(
        "Safe feed survived downgrade marker",
        "https://example.test/safe-feed",
    )
    feed_stub.set_response("/safe.xml", rss_feed([entry]))
    profile_writer(feeds=[feed_stub.url("/redirect.xml"), feed_stub.url("/safe.xml")])
    certificate, _ = tls_certificate

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

    assert result.returncode == 0, (
        f"Safe feed must remain usable after redirect rejection: {result.stderr}"
    )
    prompt = json.dumps(model_stub.state.snapshot())
    assert "Safe feed survived downgrade marker" in prompt, (
        "The unaffected feed must still reach the model"
    )
    log = (data_dir / "run.log").read_text(encoding="utf-8").lower()
    assert "redirect" in log or "http://" in log, "Downgrade refusal must be logged"
    assert not any(request.get("method") == "GET" for request in model_stub.state.snapshot()), (
        "The client must not follow the redirect to the plain-HTTP server"
    )
    assert "Downgraded feed marker must not appear" not in prompt, (
        "Content from the downgraded HTTP feed must not reach the model"
    )


def test_r19_default_cap_is_three_newest_entries_per_feed(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    rss_feed,
    env_builder,
) -> None:
    """R19: at most three entries per feed are passed, newest first by date."""
    entries = [
        make_entry(
            f"Per-feed cap marker {index}",
            f"https://example.test/cap/{index}",
            days_ago=index,
        )
        for index in range(5)
    ]
    feed_stub.set_response("/feed.xml", rss_feed(entries))
    profile_writer(feeds=[feed_stub.url()])
    certificate, _ = tls_certificate

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

    assert result.returncode == 0, f"Feed cap run must succeed: {result.stderr}"
    prompt = json.dumps(model_stub.state.snapshot())
    for index in range(3):
        assert f"Per-feed cap marker {index}" in prompt, (
            "One of the three newest entries must reach the model"
        )
    for index in (3, 4):
        assert f"Per-feed cap marker {index}" not in prompt, (
            "Older entries beyond the default cap must be excluded"
        )


def test_r19_configured_cap_is_applied_per_feed(
    run_cli,
    model_stub,
    feed_stub,
    profile_writer,
    tls_certificate,
    rss_feed,
    env_builder,
) -> None:
    """R19: AI_POST_RSS_PER_FEED configures the entry cap."""
    first = [
        make_entry(
            f"First-feed cap marker {index}",
            f"https://example.test/first/{index}",
            days_ago=index,
        )
        for index in range(4)
    ]
    second = [
        make_entry(
            f"Second-feed cap marker {index}",
            f"https://example.test/second/{index}",
            days_ago=index,
        )
        for index in range(4)
    ]
    feed_stub.set_response("/first.xml", rss_feed(first))
    feed_stub.set_response("/second.xml", rss_feed(second))
    profile_writer(feeds=[feed_stub.url("/first.xml"), feed_stub.url("/second.xml")])
    certificate, _ = tls_certificate

    result = run_cli(
        "--provider",
        "openai-compat",
        "--search",
        "rss",
        env=env_builder(
            OPENAI_COMPAT_BASE_URL=model_stub.base_url,
            OPENAI_COMPAT_MODEL="test-model",
            SSL_CERT_FILE=str(certificate),
            AI_POST_RSS_PER_FEED="2",
        ),
    )

    assert result.returncode == 0, f"Configured cap must succeed: {result.stderr}"
    prompt = json.dumps(model_stub.state.snapshot())

    for index in range(2):
        assert f"First-feed cap marker {index}" in prompt, (
            "Configured cap must include the newest entries from the first feed"
        )
        assert f"Second-feed cap marker {index}" in prompt, (
            "Configured cap must include the newest entries from the second feed"
        )
    for index in (2, 3):
        assert f"First-feed cap marker {index}" not in prompt, (
            "Configured cap must exclude older entries from the first feed"
        )
        assert f"Second-feed cap marker {index}" not in prompt, (
            "Configured cap must exclude older entries from the second feed"
        )

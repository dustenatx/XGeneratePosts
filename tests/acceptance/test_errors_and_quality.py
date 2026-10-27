"""Expected failures, provider timeouts, secret handling, and license checks."""

from __future__ import annotations

import json
import time

from conftest import REPO_ROOT


def test_r12_model_http_error_is_readable_and_has_no_traceback(
    run_cli,
    model_stub,
    successful_rss_environment,
) -> None:
    """R12: model HTTP errors fail cleanly with a readable message."""
    model_stub.state.status = 500
    model_stub.state.body = b'{"error":"simulated provider failure"}'

    result = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(),
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, "Model HTTP error must fail"
    assert output.strip(), "Model HTTP error must produce a readable message"
    assert "Traceback (most recent call last)" not in output, (
        "Expected provider failure must not print a traceback"
    )
    assert result.log_lines_added == 1, (
        "Expected provider failure must add exactly one run.log line"
    )


def test_r20_provider_timeout_is_honoured(
    run_cli,
    model_stub,
    successful_rss_environment,
) -> None:
    """R20: provider timeout override ends a stalled request promptly."""
    model_stub.state.delay = 4.0
    started = time.monotonic()

    result = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(AI_POST_PROVIDER_TIMEOUT="1"),
        timeout=10,
    )
    elapsed = time.monotonic() - started
    output = result.stdout + result.stderr

    assert result.returncode != 0, "Timed-out provider request must fail"
    assert elapsed < 3.5, (
        f"Provider timeout must interrupt the delayed request; elapsed={elapsed:.2f}s"
    )
    assert output.strip(), "Timeout failure must be readable"
    assert "Traceback (most recent call last)" not in output, (
        "Expected timeout failure must not print a traceback"
    )
    assert result.log_lines_added == 1, "Expected timeout failure must add exactly one run.log line"


def test_secrets_do_not_leak_on_provider_failure(
    run_cli,
    model_stub,
    successful_rss_environment,
    data_dir,
) -> None:
    """Definition of done 4: secret sentinel is absent from failure output and files."""
    sentinel = "secret-sentinel-provider-failure"
    model_stub.state.status = 500
    model_stub.state.body = json.dumps({"error": "deliberate provider failure"}).encode()

    result = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(OPENAI_COMPAT_API_KEY=sentinel),
    )
    observed = result.stdout + result.stderr

    assert result.returncode != 0, "Simulated provider error must fail"
    for filename in ("run.log", "drafts.md", "history.json"):
        path = data_dir / filename
        if path.exists():
            observed += path.read_text(encoding="utf-8")

    assert sentinel not in observed, (
        "API key must not appear in output or persistent files on failure"
    )
    assert result.log_lines_added == 1, (
        "Expected provider failure must add exactly one run.log line"
    )


def test_r16_license_exists_and_contains_mit_license() -> None:
    """R16: root LICENSE file contains the MIT license."""
    license_path = REPO_ROOT / "LICENSE"

    assert license_path.is_file(), "LICENSE must exist at repository root"
    content = license_path.read_text(encoding="utf-8")
    assert "MIT License" in content, "LICENSE must identify the MIT license"
    assert "Permission is hereby granted, free of charge" in content, (
        "LICENSE must contain the MIT permission grant"
    )
    assert "THE SOFTWARE IS PROVIDED" in content, "LICENSE must contain the MIT warranty disclaimer"


def test_missing_topic_without_terminal_is_an_expected_failure(
    env_builder, run_cli, profile_writer, model_stub
) -> None:
    """Section 11 preconditions: no topic and no terminal is an expected failure."""
    # A local, closed port: nothing on the internet is reachable even if fetched.
    profile_writer(feeds=["https://127.0.0.1:9/feed.xml"])
    result = run_cli(
        "--no-default-topic",
        "--provider",
        "openai-compat",
        env=env_builder(
            OPENAI_COMPAT_BASE_URL=model_stub.base_url,
            OPENAI_COMPAT_MODEL="test-model",
        ),
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, "A drafting run without a topic or terminal must fail"
    assert "--topic" in output, "The message must say how to give a topic"
    assert "Traceback (most recent call last)" not in output, (
        "Expected missing-topic failure must not print a traceback"
    )
    assert not model_stub.state.snapshot(), "No model request may be made without a topic"

"""Provider selection, credentials, HTTP contract, and standard-library tests."""

from __future__ import annotations

import pytest


def test_r1_r3_default_provider_requires_groq_credential(
    env_builder, run_cli, profile_writer
) -> None:
    """R1, R3: default provider is Groq and reports its missing credential."""
    profile_writer(feeds=[])
    result = run_cli(env=env_builder())

    assert result.returncode != 0, "Missing default Groq credential must fail"
    output = result.stdout + result.stderr
    assert "GROQ_API_KEY" in output, "Failure must name GROQ_API_KEY"
    assert "groq" in output.lower(), "Failure must identify the selected provider"
    assert "https://console.groq.com/keys" in output, (
        "Missing Groq credential message must contain the key-creation URL"
    )
    assert "Traceback (most recent call last)" not in output, (
        "Expected credential failure must not print a traceback"
    )
    assert result.log_lines_added == 1, (
        "Expected credential failure must add exactly one run.log line"
    )


@pytest.mark.parametrize(
    ("args", "overrides", "key_name", "provider", "key_url"),
    [
        (
            ("--provider", "anthropic"),
            {"AI_POST_PROVIDER": "openai-compat"},
            "ANTHROPIC_API_KEY",
            "anthropic",
            "https://console.anthropic.com/settings/keys",
        ),
        (
            (),
            {"AI_POST_PROVIDER": "anthropic"},
            "ANTHROPIC_API_KEY",
            "anthropic",
            "https://console.anthropic.com/settings/keys",
        ),
        (
            (),
            {},
            "GROQ_API_KEY",
            "groq",
            "https://console.groq.com/keys",
        ),
    ],
)
def test_r1_r3_provider_precedence_and_missing_key_guidance(
    env_builder,
    run_cli,
    profile_writer,
    args: tuple[str, ...],
    overrides: dict[str, str],
    key_name: str,
    provider: str,
    key_url: str,
) -> None:
    """R1, R3: provider flag overrides environment, which overrides default."""
    profile_writer(feeds=[])
    result = run_cli(*args, env=env_builder(**overrides))
    output = result.stdout + result.stderr

    assert result.returncode != 0, "Missing selected-provider credential must fail"
    assert provider in output.lower(), "Error must identify the selected provider"
    assert key_name in output, f"Error must name {key_name}"
    assert key_url in output, f"Error must include {key_url}"
    assert "Traceback (most recent call last)" not in output, (
        "Expected missing-key failure must not print a traceback"
    )
    assert result.log_lines_added == 1, (
        "Expected missing-key failure must add exactly one run.log line"
    )


def test_r3_other_provider_key_does_not_enable_fallback(
    env_builder, run_cli, profile_writer
) -> None:
    """R3: an Anthropic key cannot satisfy missing Groq credentials."""
    profile_writer(feeds=[])
    result = run_cli(env=env_builder(ANTHROPIC_API_KEY="not-a-groq-key"))
    output = result.stdout + result.stderr

    assert result.returncode != 0, "Groq must fail without GROQ_API_KEY"
    assert "GROQ_API_KEY" in output, "Error must request the Groq credential"
    assert "https://console.groq.com/keys" in output, "Error must include the Groq key-creation URL"
    assert result.log_lines_added == 1, (
        "Expected missing-key failure must add exactly one run.log line"
    )


def test_r4_openai_compat_end_to_end_request_shape(
    run_cli,
    model_stub,
    successful_rss_environment,
) -> None:
    """R4: OpenAI-compatible provider sends the documented wire format."""
    result = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(),
    )

    assert result.returncode == 0, f"OpenAI-compatible run must succeed: {result.stderr}"
    requests = model_stub.state.snapshot()
    assert len(requests) == 1, "A run must make one model request"
    request = requests[0]

    assert request["method"] == "POST", "Model request must use POST"
    assert request["path"] == "/v1/chat/completions", (
        "Model request must target /v1/chat/completions"
    )
    assert isinstance(request["body"], dict), "Request body must be JSON"
    assert request["body"].get("model") == "test-model", (
        "Request body must include the configured model"
    )
    assert isinstance(request["body"].get("messages"), list), (
        "Request body must include a messages list"
    )
    assert request["headers"].get("Content-Type", "").lower().startswith("application/json"), (
        "Request must declare JSON content"
    )
    assert "A useful security engineering development worth watching." in result.stdout, (
        "Successful run must display the X draft"
    )
    assert (
        "A useful security engineering development, with context for practitioners."
        in result.stdout
    ), "Successful run must display the LinkedIn draft"


def test_r4_optional_credential_is_sent_as_bearer(
    run_cli,
    model_stub,
    successful_rss_environment,
) -> None:
    """R4: optional OpenAI-compatible API key is sent as a Bearer token."""
    result = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(OPENAI_COMPAT_API_KEY="compat-sentinel-key"),
    )

    assert result.returncode == 0, "Configured local provider must succeed"
    request = model_stub.state.snapshot()[0]
    assert request["headers"].get("Authorization") == ("Bearer compat-sentinel-key"), (
        "Configured key must be sent as a Bearer token"
    )


def test_r4_missing_openai_compat_configuration_fails_cleanly(env_builder, run_cli) -> None:
    """R4: OpenAI-compatible mode requires its configured endpoint and model."""
    result = run_cli(
        "--provider",
        "openai-compat",
        env=env_builder(),
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, "Missing provider configuration must fail"
    assert "Traceback (most recent call last)" not in output, (
        "Configuration failure must not print a traceback"
    )
    assert result.log_lines_added == 1, (
        "Expected configuration failure must add exactly one run.log line"
    )


def test_r4_non_loopback_plain_http_endpoint_is_rejected(env_builder, run_cli) -> None:
    """R4: plain HTTP is allowed only for localhost and 127.0.0.1."""
    result = run_cli(
        "--provider",
        "openai-compat",
        env=env_builder(
            OPENAI_COMPAT_BASE_URL="http://example.invalid/v1",
            OPENAI_COMPAT_MODEL="test-model",
        ),
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, "Non-loopback HTTP endpoint must be rejected"
    assert "Traceback (most recent call last)" not in output, "Rejected endpoint must fail cleanly"
    assert result.log_lines_added == 1, (
        "Expected endpoint failure must add exactly one run.log line"
    )


def test_r5_openai_compat_end_to_end_under_python_no_site(
    run_cli,
    model_stub,
    successful_rss_environment,
) -> None:
    """R5: OpenAI-compatible provider succeeds under Python -S."""
    result = run_cli(
        "--provider",
        "openai-compat",
        env=successful_rss_environment(),
        python_flags=("-S",),
    )

    assert result.returncode == 0, f"Provider must run without site-packages: {result.stderr}"
    assert len(model_stub.state.snapshot()) == 1, (
        "Standard-library provider must reach the model stub"
    )


def test_r5_groq_missing_credential_path_under_python_no_site(
    env_builder, run_cli, profile_writer
) -> None:
    """R5: Groq credential validation does not require site-packages."""
    profile_writer(feeds=[])
    result = run_cli(
        "--provider",
        "groq",
        env=env_builder(),
        python_flags=("-S",),
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, "Groq without its credential must fail"
    assert "GROQ_API_KEY" in output, "Failure must identify the missing key"
    assert "Traceback (most recent call last)" not in output, (
        "Credential validation must not fail with an import traceback"
    )
    assert result.log_lines_added == 1, (
        "Expected credential failure must add exactly one run.log line"
    )

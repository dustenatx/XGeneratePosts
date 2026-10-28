"""R48: a missing optional SDK names its extra and both install routes, never a version."""

import re
import sys
import tomllib
from pathlib import Path

import pytest

from xgenerateposts import providers, publish

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTRAS = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
    "optional-dependencies"
]


def assert_names_extra_and_both_routes(message: str, extra: str) -> None:
    assert f"uv tool install --reinstall '.[{extra}]'" in message
    assert f"~/.ai_post_venv/bin/pip install -e '.[{extra}]'" in message
    # The pin lives only in pyproject.toml, so Dependabot bumps need no text edits.
    assert not re.search(r"==\s*\d", message)
    for requirement in EXTRAS[extra]:
        assert requirement.split("==")[1] not in message


def test_extras_are_declared_and_pinned_exactly():
    assert set(EXTRAS) == {"anthropic", "x"}
    assert [r.split("==")[0] for r in EXTRAS["anthropic"]] == ["anthropic"]
    assert [r.split("==")[0] for r in EXTRAS["x"]] == ["tweepy"]
    assert all(r.count("==") == 1 for reqs in EXTRAS.values() for r in reqs)


def test_missing_anthropic_names_its_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(SystemExit) as exc:
        providers.AnthropicProvider().generate("prompt")
    assert "--provider anthropic" in exc.value.code
    assert_names_extra_and_both_routes(exc.value.code, "anthropic")


def test_missing_tweepy_names_its_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "tweepy", None)
    with pytest.raises(SystemExit) as exc:
        publish.post_to_x("post")
    assert "--post" in exc.value.code
    assert_names_extra_and_both_routes(exc.value.code, "x")

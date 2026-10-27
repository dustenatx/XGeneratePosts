"""R33: xgp init creates the data directory and a mode-600 profile, and never
overwrites one that exists."""

import stat
import sys
from importlib import resources

import pytest

from xgenerateposts import cli, config

EXAMPLE = resources.files("xgenerateposts").joinpath(config.EXAMPLE_PROFILE).read_bytes()


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def run_init(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["xgp", "init"])
    cli.run()


def test_creates_directory_and_profile_with_mode_600(monkeypatch, tmp_path, capsys):
    data = tmp_path / "new" / "XPosts"
    monkeypatch.setenv("AI_POST_DATA_DIR", str(data))

    run_init(monkeypatch)

    profile = data / "author_profile.md"
    assert profile.read_bytes() == EXAMPLE
    assert mode(profile) == 0o600
    assert str(profile) in capsys.readouterr().out


def test_new_data_directory_gets_mode_700(monkeypatch, tmp_path):
    data = tmp_path / "XPosts"
    monkeypatch.setenv("AI_POST_DATA_DIR", str(data))

    run_init(monkeypatch)

    assert mode(data) == 0o700


def test_existing_data_directory_keeps_its_mode(monkeypatch, tmp_path):
    data = tmp_path / "XPosts"
    data.mkdir()
    data.chmod(0o755)
    monkeypatch.setenv("AI_POST_DATA_DIR", str(data))

    run_init(monkeypatch)

    assert mode(data) == 0o755
    assert (data / "author_profile.md").read_bytes() == EXAMPLE


def test_existing_profile_is_left_byte_identical(monkeypatch, tmp_path, capsys):
    profile = tmp_path / "author_profile.md"
    profile.write_bytes(b"## Beat\nmine\n\n## Voice\nmine\n")
    profile.chmod(0o644)
    before = sorted(p.name for p in tmp_path.iterdir())

    with pytest.raises(SystemExit) as exc:
        monkeypatch.setattr(sys, "argv", ["xgp", "init"])
        cli.main()

    assert exc.value.code != 0
    assert profile.read_bytes() == b"## Beat\nmine\n\n## Voice\nmine\n"
    assert mode(profile) == 0o644
    assert sorted(p.name for p in tmp_path.iterdir()) == before  # no run.log either
    assert "already exists" in capsys.readouterr().err


def test_honors_ai_post_data_dir(monkeypatch, tmp_path):
    data = tmp_path / "custom"
    monkeypatch.setenv("AI_POST_DATA_DIR", str(data))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    run_init(monkeypatch)

    assert (data / "author_profile.md").exists()
    assert not (tmp_path / "home" / "XPosts").exists()


def test_defaults_to_xposts_in_home(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_POST_DATA_DIR")
    monkeypatch.setenv("HOME", str(tmp_path))

    run_init(monkeypatch)

    assert (tmp_path / "XPosts" / "author_profile.md").read_bytes() == EXAMPLE

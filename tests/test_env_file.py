"""Which settings the env file may set: AI_POST_DATA_DIR yes, AI_POST_ENV_FILE no."""

import os
import sys

from xgenerateposts import cli, config


def test_data_dir_set_only_in_the_env_file_is_honored(monkeypatch, tmp_path, capsys):
    data = tmp_path / "from-env-file"
    data.mkdir()
    (data / "author_profile.md").write_text("## Topics\n- Only here\n\n## Beat\nb\n\n## Voice\nv\n")
    env_file = tmp_path / "test.env"
    env_file.write_text(f"export AI_POST_DATA_DIR={data}\n")
    monkeypatch.setenv("AI_POST_ENV_FILE", str(env_file))
    monkeypatch.setenv("HOME", str(tmp_path))  # if the file were ignored: tmp, never ~/XPosts
    monkeypatch.delenv("AI_POST_DATA_DIR")
    monkeypatch.setattr(sys, "argv", ["daily_post.py", "--list-topics"])

    cli.run()

    assert capsys.readouterr().out == " 1. Only here\n"
    assert config.data_dir() == data


def test_env_file_location_set_inside_the_env_file_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AI_POST_ENV_FILE")
    default = tmp_path / ".ai_post_env"
    default.write_text(f"export AI_POST_ENV_FILE={tmp_path / 'elsewhere.env'}\n")

    config.load_env_file()

    assert config.env_file() == default
    assert "AI_POST_ENV_FILE" not in os.environ

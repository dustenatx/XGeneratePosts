from importlib import resources
from pathlib import Path

import pytest

from xgenerateposts import config, search, storage


def write(tmp_path, text):
    path = tmp_path / "p.md"
    path.write_text(text)
    return path


def test_sections_parsed_case_insensitively(tmp_path):
    profile = storage.load_profile(write(tmp_path, "## BEAT\nb\n\n## Voice\nv\n\n## Notes\nmine\n"))
    assert profile["beat"] == "b"
    assert profile["voice"] == "v"


def test_missing_required_section_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        storage.load_profile(write(tmp_path, "## Beat\nb\n"))
    assert "## Voice" in exc.value.code


def test_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        storage.load_profile(tmp_path / "absent.md")
    assert "xgp init" in exc.value.code
    assert "xgenerateposts/author_profile.example.md" in exc.value.code


def test_example_profile_parses():
    """The packaged example, the one file xgp init copies, parses as a profile."""
    example = resources.files("xgenerateposts").joinpath(config.EXAMPLE_PROFILE)
    profile = storage.load_profile(Path(str(example)))
    assert search.parse_feeds(profile) == [
        "https://blog.example.com/feed.xml",
        "https://news.example.org/atom.xml",
    ]

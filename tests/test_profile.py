import pytest

import daily_post as d


def write(tmp_path, text):
    path = tmp_path / "p.md"
    path.write_text(text)
    return path


def test_sections_parsed_case_insensitively(tmp_path):
    profile = d.load_profile(write(tmp_path, "## BEAT\nb\n\n## Voice\nv\n\n## Notes\nmine\n"))
    assert profile["beat"] == "b"
    assert profile["voice"] == "v"


def test_missing_required_section_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        d.load_profile(write(tmp_path, "## Beat\nb\n"))
    assert "## Voice" in exc.value.code


def test_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        d.load_profile(tmp_path / "absent.md")
    assert "author_profile.example.md" in exc.value.code


def test_example_profile_parses():
    profile = d.load_profile(d.Path(__file__).parent.parent / "author_profile.example.md")
    assert d.parse_feeds(profile) == [
        "https://blog.example.com/feed.xml",
        "https://news.example.org/atom.xml",
    ]

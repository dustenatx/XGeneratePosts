import pytest

import daily_post as d
from tests.conftest import MODEL_OUTPUT


def test_parse_fields_ignores_text_before_first_delimiter():
    fields = d.parse_fields(MODEL_OUTPUT)
    assert fields["url"] == "https://vendor.example/post"
    assert fields["title"] == "A Real Release"
    assert "end" not in fields


def test_parse_fields_keeps_quotes_and_line_breaks():
    fields = d.parse_fields(MODEL_OUTPUT)
    assert fields["linkedin"].startswith("A longer take")
    assert "\n\nWhat would you ask first?" in fields["linkedin"]


def test_parse_fields_rejects_unformatted_text():
    with pytest.raises(ValueError):
        d.parse_fields("Here is a post about a thing.")


def test_trim_leaves_short_text():
    assert d.trim("  short  ", 20) == "short"


def test_trim_cuts_at_sentence_boundary():
    text = "First sentence is here. Second sentence runs on and on."
    assert d.trim(text, 30) == "First sentence is here."


def test_trim_falls_back_to_word_boundary():
    text = "word " * 20
    out = d.trim(text, 23)
    assert out.endswith("…")
    assert len(out) <= 24
    assert not out[:-1].endswith(" ")

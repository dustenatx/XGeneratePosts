"""The model's delimited response, and the posts made from it. No I/O."""

import re

FIELD_PATTERN = re.compile(r"^===([A-Z]+)===\s*$", re.MULTILINE)


def parse_fields(text: str) -> dict[str, str]:
    """Parse the delimited model response into a dict.

    Delimiters rather than JSON: post text routinely contains quotes,
    apostrophes, and line breaks, all of which need escaping inside a JSON
    string and break the parse whenever the model gets that wrong.
    """
    parts = FIELD_PATTERN.split(text)
    if len(parts) < 3:
        raise ValueError(f"Model output was not in the expected format:\n{text[:500]}")
    fields = {}
    for name, body in zip(parts[1::2], parts[2::2], strict=False):
        if name != "END":
            fields[name.lower()] = body.strip()
    return fields


def trim(text: str, limit: int) -> str:
    """Trim at a sentence boundary where possible so drafts never end
    mid-word."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for boundary in (". ", ".\n", "! ", "? "):
        idx = cut.rfind(boundary)
        if idx > limit * 0.6:
            return cut[: idx + 1].strip()
    return cut[: cut.rfind(" ")].strip() + "…"


def compose_posts(item: dict[str, str]) -> tuple[str, str]:
    return f"{item['tweet']}\n{item['url']}", f"{item['linkedin']}\n\n{item['url']}"

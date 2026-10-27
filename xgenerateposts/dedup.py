"""What has already been used, by URL or by title (R17). No I/O."""


def normalize_title(title: str | None) -> str:
    """Case-folded, whitespace collapsed (R17)."""
    return " ".join((title or "").casefold().split())


def used_from(history: list) -> tuple:
    """(used URLs, used titles) from history.json entries, oldest first."""
    return (
        [h["url"] for h in history if h.get("url")],
        [h["title"] for h in history if h.get("title")],
    )


def is_used(url: str, title: str | None, used_urls: list, used_titles: list) -> bool:
    """True if the URL, or the normalized title, has been used before (R17)."""
    if url in used_urls:
        return True
    title = normalize_title(title)
    return bool(title) and title in {normalize_title(t) for t in used_titles}

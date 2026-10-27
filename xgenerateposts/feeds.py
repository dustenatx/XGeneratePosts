"""Feed parsing, cleaning and ranking for --search rss. No I/O."""

import html
import pyexpat
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

STOP_WORDS = frozenset(
    {"and", "the", "for", "with", "from", "into", "about", "that", "this", "are", "its", "how"}
)
RSS_SUMMARY_CHARS = 300
# Expat below 2.7.2 may be open to billion-laughs, quadratic-blowup and
# large-token attacks (https://docs.python.org/3/library/xml.html#xml-security).
MIN_EXPAT = (2, 7, 2)


def require_expat() -> None:
    """Refuse to parse untrusted XML with an Expat that lacks entity-expansion
    protection (R21)."""
    if pyexpat.version_info < MIN_EXPAT:
        need = ".".join(map(str, MIN_EXPAT))
        have = ".".join(map(str, pyexpat.version_info))
        raise SystemExit(
            f"\n--search rss needs Expat {need} or newer, which protects against\n"
            f"  entity-expansion attacks in feed XML. This Python has Expat {have}\n"
            f"  ({pyexpat.EXPAT_VERSION}). Use a newer Python, or --search native.\n"
        )


def clean_text(text: str | None, limit: int = RSS_SUMMARY_CHARS) -> str:
    """Feed text as plain prose: no markup, no delimiters, bounded length."""
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]*>", " ", text)
    text = text.replace("<", " ").replace(">", " ").replace("===", "=")
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    try:
        parsed = parsedate_to_datetime(text)  # RSS: RFC 822
    except TypeError, ValueError:
        try:
            parsed = datetime.fromisoformat(text)  # Atom: RFC 3339
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


ATOM = "{http://www.w3.org/2005/Atom}"


def parse_feed(data: bytes) -> list:
    """Entries from RSS 2.0 or Atom XML: dicts of title, link, date, summary.

    The caller has already checked the Expat version (require_expat).
    """
    root = ET.fromstring(data)  # noqa: S314 - Expat >= 2.7.2 enforced by require_expat
    entries: list[dict] = []
    if root.tag == "rss":
        for item in root.iterfind("./channel/item"):
            entries.append(
                {
                    "title": item.findtext("title"),
                    "link": (item.findtext("link") or "").strip(),
                    "date": parse_date(item.findtext("pubDate")),
                    "summary": item.findtext("description"),
                }
            )
    elif root.tag == f"{ATOM}feed":
        for entry in root.iterfind(f"{ATOM}entry"):
            link = ""
            for el in entry.iterfind(f"{ATOM}link"):
                if el.get("rel", "alternate") == "alternate":
                    link = (el.get("href") or "").strip()
                    break
            entries.append(
                {
                    "title": entry.findtext(f"{ATOM}title"),
                    "link": link,
                    "date": parse_date(
                        entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated")
                    ),
                    "summary": entry.findtext(f"{ATOM}summary") or entry.findtext(f"{ATOM}content"),
                }
            )
    else:
        raise ValueError(f"not an RSS 2.0 or Atom feed (root element {root.tag!r})")
    return [e for e in entries if e["link"] and clean_text(e["title"])]


def newest(entries: list, limit: int) -> list:
    """Newest first; undated entries keep feed order after dated ones (R19)."""
    floor = datetime.min.replace(tzinfo=UTC)
    return sorted(entries, key=lambda e: e["date"] or floor, reverse=True)[:limit]


def words(text: str) -> set:
    """Lower-cased words of 3+ characters, stop words removed (R22)."""
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3} - STOP_WORDS


def ranked(entries: list, topic: str, limit: int) -> list:
    """Most topic words in title or summary first, then newest first; undated
    entries go last within a score, in feed order (R22)."""
    wanted = words(topic)
    floor = datetime.min.replace(tzinfo=UTC)

    def key(e: dict) -> tuple:
        found = words(f"{clean_text(e['title'])} {clean_text(e['summary'])}")
        return len(wanted & found), e["date"] or floor

    return sorted(entries, key=key, reverse=True)[:limit]


def format_candidates(entries: list) -> str:
    blocks = []
    for n, e in enumerate(entries, 1):
        when = e["date"].date().isoformat() if e["date"] else "unknown"
        blocks.append(
            f"[{n}] Title: {clean_text(e['title'], 200)}\n"
            f"    Link: {clean_text(e['link'], 500)}\n"
            f"    Date: {when}\n"
            f"    Feed: {e['feed']}\n"
            f"    Summary: {clean_text(e['summary'])}"
        )
    return "\n".join(blocks)

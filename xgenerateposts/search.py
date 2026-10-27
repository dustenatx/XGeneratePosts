"""Search sources: each returns the candidate items as prompt text, or None
when the provider searches the web itself."""

import re
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

from xgenerateposts import config, net
from xgenerateposts.config import (
    FEED_TIMEOUT,
    HTTP_USER_AGENT,
    MAX_FEED_BYTES,
    NATIVE_SEARCH_PROVIDERS,
    NOTHING_LOST,
    SEARCH_SOURCES,
)
from xgenerateposts.dedup import is_used
from xgenerateposts.feeds import format_candidates, newest, parse_feed, ranked, require_expat
from xgenerateposts.storage import warn


def select_search(flag: str | None, provider_name: str) -> str:
    """--search, then AI_POST_SEARCH, then the provider's default (R6)."""
    default = "native" if provider_name in NATIVE_SEARCH_PROVIDERS else "rss"
    name = (flag or config.search_setting() or default).strip().lower()
    if name not in SEARCH_SOURCES:
        raise SystemExit(
            f"\nUnknown search source {name!r} (from AI_POST_SEARCH). "
            f"Choose one of: {', '.join(SEARCH_SOURCES)}.\n"
        )
    if name == "native" and provider_name not in NATIVE_SEARCH_PROVIDERS:
        raise SystemExit(
            f"\n--provider {provider_name} has no server-side search.\n"
            "  Use --search rss with a '## Feeds' section in your profile.\n"
        )
    return name


class NativeSearch:
    """The provider searches server-side; nothing to add to the prompt."""

    name = "native"

    def candidates(self, used_urls: list, used_titles: list, topic: str) -> str | None:
        return None


def parse_feeds(profile: dict) -> list:
    """Feed URLs from the profile's '## Feeds' section (R8, R9). One per line;
    bullets are stripped and lines that are not URLs are ignored as notes.
    Only https:// URLs are used."""
    raw = profile.get("feeds", "")
    lines = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if "://" in line.split(" ", 1)[0]:
            lines.append(line.split()[0])
    if not lines:
        raise SystemExit(
            "\n--search rss needs a '## Feeds' section in your author profile,\n"
            "  with one feed URL per line, for example:\n\n"
            "    ## Feeds\n"
            "    - https://blog.example.com/feed.xml\n\n"
            "  Or use --search native with a provider that searches the web.\n"
        )
    feeds = []
    for url in lines:
        if url.lower().startswith("https://"):
            feeds.append(url)
        else:
            warn(f"feed skipped, not https: {url}")
    if not feeds:
        raise SystemExit("\nNo https:// feed URLs in the '## Feeds' section.\n")
    return feeds


def fetch_feed(url: str) -> bytes:
    request = urllib.request.Request(  # noqa: S310 - parse_feeds admits only https:// URLs
        url,
        headers={
            "User-Agent": HTTP_USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.1",
        },
    )
    # Only identity encoding is requested (urllib's default Accept-Encoding:
    # identity) and urllib never decompresses, so a compressed "decompression
    # bomb" is never expanded.
    with net.HTTP_OPENER.open(request, timeout=FEED_TIMEOUT) as response:
        return net.read_capped(response, MAX_FEED_BYTES)


class RssSearch:
    """Candidate items from the feeds in the profile's '## Feeds' section."""

    name = "rss"

    def __init__(self, profile: dict) -> None:
        require_expat()
        self.feeds = parse_feeds(profile)
        self.per_feed = config.rss_per_feed()
        self.max_entries = config.rss_max_entries()
        self.links: set[str] = set()

    def candidates(self, used_urls: list, used_titles: list, topic: str) -> str:
        picked = []
        for url in self.feeds:
            try:
                entries = parse_feed(fetch_feed(url))
            except net.InsecureRedirectError as exc:
                warn(f"feed skipped, {exc.reason}: {url}")
                continue
            except (OSError, ValueError, ET.ParseError) as exc:
                # URLError, HTTPError and timeouts are all OSError.
                warn(f"feed skipped, {type(exc).__name__}: {exc}: {url}")
                continue
            fresh = [
                e for e in entries if not is_used(e["link"], e["title"], used_urls, used_titles)
            ]
            for entry in newest(fresh, self.per_feed):
                entry["feed"] = urlsplit(url).hostname or url
                picked.append(entry)

        if not picked:
            raise SystemExit(
                f"\nNo feed yielded a new entry ({len(self.feeds)} tried). "
                f"The reasons are in {config.log_file()}.\n\n  {NOTHING_LOST}\n"
            )
        picked = ranked(picked, topic, self.max_entries)
        self.links = {e["link"] for e in picked}
        return format_candidates(picked)


def make_search(name: str, profile: dict):
    return RssSearch(profile) if name == "rss" else NativeSearch()

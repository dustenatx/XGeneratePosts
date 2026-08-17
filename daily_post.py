#!/usr/bin/env python3
"""
daily_post.py

Picks a technology topic, finds one noteworthy recent item on it, and drafts
two posts from that same source:

  * X/Twitter — short, link-forward, hashtagged.
  * LinkedIn  — longer, first-person point of view on why the item matters.

The topic is chosen at run time: pass --topic, or answer the numbered menu.
The menu comes from the '## Topics' section of your author profile if you
have one, otherwise from TOPIC_CATALOG below.

What makes the posts sound like YOU is an author profile file kept outside
this repo (default: ~/XPosts/author_profile.md). See author_profile.example.md
for a scaffold and instructions.

Default behavior is draft-only: both posts are printed and appended to
drafts.md for you to review and post yourself. Optional flags can publish to
X (--post) or LinkedIn (--post-linkedin).

Requirements:
    pip install anthropic        (tweepy additionally, only for --post)

Credentials are read from ~/.ai_post_env — see README.md.
"""

import argparse
import json
import os
import random
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-6"

DATA_DIR = Path(os.environ.get("AI_POST_DATA_DIR", Path.home() / "XPosts"))
PROFILE_FILE = DATA_DIR / "author_profile.md"   # your voice — never in the repo
HISTORY_FILE = DATA_DIR / "history.json"        # URLs already used (dedup)
DRAFTS_FILE = DATA_DIR / "drafts.md"            # running log of drafts
LOG_FILE = DATA_DIR / "run.log"                 # one line per run
ENV_FILE = Path(os.environ.get("AI_POST_ENV_FILE", Path.home() / ".ai_post_env"))

CONSOLE_BILLING = "https://console.anthropic.com/settings/billing"
CONSOLE_KEYS = "https://console.anthropic.com/settings/keys"

MAX_TWEET_TEXT = 255       # 280 minus ~24 chars X reserves for a t.co link
MAX_LINKEDIN_TEXT = 1100   # hard ceiling; the prompt targets 750-950

# Fallback topic menu. Override it with a '## Topics' section in your profile —
# one topic per line, optionally "Label — extra scoping detail".
TOPIC_CATALOG = [
    "AI and machine learning in the enterprise",
    "Cybersecurity and threat defense",
    "Cloud infrastructure and architecture",
    "Platform engineering and developer experience",
    "Site reliability, observability, and incident response",
    "DevOps, CI/CD, and release engineering",
    "Kubernetes and container platforms",
    "Identity and access management",
    "Data engineering and analytics platforms",
    "FinOps and cloud cost management",
    "Governance, risk, and compliance automation",
    "Agentic AI and workflow automation",
    "Networking, edge, and content delivery",
    "Engineering leadership and team practices",
]

# Profile sections. "required" ones must be present and non-empty.
PROFILE_SECTIONS = {
    "beat": True,        # audience, exclusions, what counts as a good find
    "voice": True,       # how the author thinks and sounds
    "topics": False,     # menu of technology areas to choose from
    "experience": False, # verified things the author may reference
    "never": False,      # hard rules
    "hashtags": False,   # preferred tag pool
}

# ---------------------------------------------------------------------------
# Prompt scaffolding (platform mechanics — voice comes from the profile file)
# ---------------------------------------------------------------------------

X_RULES = """
X/Twitter post rules:
- Under {max_len} characters excluding the URL (the URL is appended separately).
- Lead with what the item actually does and why the audience should care.
- One clear takeaway. Plain, confident voice. No hype words
  ("game-changer", "mind-blowing", "insane").
- 2-3 hashtags.
""".strip()

LINKEDIN_RULES = """
LinkedIn post rules:
- Target 750-950 characters INCLUDING the closing question and hashtags.
  {max_len} is a hard ceiling. Under budget beats trimmed.
- Short paragraphs, blank line between each. No markdown, no bold, no
  headers, no bullet characters — LinkedIn renders none of them.
- Open with a hook of one or two lines that earns the click on "see more":
  a specific claim, a sharp observation, a real tension, or a question with
  actual stakes. Attention must come from SUBSTANCE, not engagement bait.
  Banned openers: "Let that sink in.", "Here's the thing.", "Unpopular
  opinion:", "I'll say it.", and anything followed by a one-word paragraph
  for drama.
- Spend AT MOST one sentence describing the item; the link carries the
  details. The bulk of the post is the author's position and the takeaway.
- Take a real position: what this signals, where it will work, where it will
  fall over, what it does not solve, what must be true operationally for it
  to deliver.
- Then the value: what a practitioner or leader should DO with this — a
  question to ask a vendor, a place to pilot it, a prerequisite to fix
  first, a reason to wait.
- Close with a question that invites expert replies, not applause.
- End with 3-5 hashtags on their own line.
- Never disparage a named company. Critique the pattern, not the vendor.
""".strip()

PROMPT = """
Today is {today}. Search the web for one genuinely noteworthy item in this
technology area:

## Today's topic
{topic}

Prefer the original vendor, author, or project page over a news roundup or
aggregator.

## What counts as a good find, and for whom
{beat}

Do NOT pick any of these already-used URLs:
{used_urls}

Pick exactly ONE item — the most substantive and interesting to the audience
described. Then write TWO posts about it in the author's voice. They share a
source but are not the same post: the X version reports, the LinkedIn version
argues.

## The author's voice
{voice}
{experience}{never}{hashtags}

## Platform rules
{x_rules}

{linkedin_rules}

## Output format
Respond in EXACTLY this format, with nothing before or after it. Do not use
JSON. Do not use markdown fences. Do not add commentary. Field values are
plain text — quotes, apostrophes, and line breaks are all fine and need no
escaping.

===URL===
canonical link to the item
===TITLE===
item title
===SOURCE===
publisher or vendor
===TWEET===
X post text WITHOUT the URL
===LINKEDIN===
LinkedIn post text WITHOUT the URL
===WHY===
one sentence: why you picked it
===END===
""".strip()


# ---------------------------------------------------------------------------
# Environment and profile
# ---------------------------------------------------------------------------

def load_env_file(path: Path = ENV_FILE) -> None:
    """Load KEY=value lines (with or without a leading 'export ') into
    os.environ. Variables already set in the environment win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and key and key not in os.environ:
            os.environ[key] = value.strip().strip("'\"")


def load_profile(path: Path) -> dict:
    """Parse the author profile into {section_name: body}.

    Sections are '## Heading' blocks. Heading names are matched
    case-insensitively against PROFILE_SECTIONS; unknown sections are ignored,
    so you can keep notes to yourself in the file.
    """
    if not path.exists():
        raise SystemExit(
            f"No author profile at {path}\n"
            "Copy author_profile.example.md from the repo to that path and "
            "fill it in — it is what makes the posts sound like you."
        )

    sections, current = {}, None
    for line in path.read_text().splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1).strip().lower()
            sections[current] = []
        elif current:
            sections[current].append(line)

    parsed = {k: "\n".join(v).strip() for k, v in sections.items()}
    missing = [name for name, required in PROFILE_SECTIONS.items()
               if required and not parsed.get(name)]
    if missing:
        raise SystemExit(
            f"{path} is missing required section(s): "
            + ", ".join(f"## {m.title()}" for m in missing)
        )
    return parsed


def topic_menu(profile: dict) -> list:
    """Topics from the profile's '## Topics' section, else the built-in
    catalog. One topic per line; '-' and '*' bullets and numbering are
    stripped."""
    raw = profile.get("topics", "")
    topics = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if line and not line.startswith("#"):
            topics.append(line)
    return topics or list(TOPIC_CATALOG)


def choose_topic(topics: list, requested: str = None,
                 pick_random: bool = False) -> str:
    """Resolve the topic from --topic, --random-topic, or an interactive menu.

    --topic accepts a menu number, a case-insensitive substring of a menu
    entry, or free text that is not in the menu at all.
    """
    if pick_random:
        return random.choice(topics)

    if requested:
        if requested.isdigit() and 1 <= int(requested) <= len(topics):
            return topics[int(requested) - 1]
        matches = [t for t in topics if requested.lower() in t.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SystemExit("Ambiguous --topic. Matches:\n  "
                             + "\n  ".join(matches))
        return requested  # free-text topic, not in the menu

    if not sys.stdin.isatty():
        raise SystemExit("No topic given and no terminal to ask on. Use "
                         "--topic \"...\" or --random-topic.")

    print("\nPick a topic for today:\n")
    for i, topic in enumerate(topics, 1):
        print(f"  {i:>2}. {topic}")
    print("\n   r. Random")
    print("   Or type any topic of your own.\n")

    answer = input("Topic: ").strip()
    if not answer:
        raise SystemExit("No topic chosen.")
    if answer.lower() == "r":
        return random.choice(topics)
    if answer.isdigit() and 1 <= int(answer) <= len(topics):
        return topics[int(answer) - 1]
    return answer


def build_prompt(profile: dict, topic: str, used_urls: list) -> str:
    def block(title: str, key: str) -> str:
        body = profile.get(key, "").strip()
        return f"\n\n## {title}\n{body}" if body else ""

    return PROMPT.format(
        today=date.today().isoformat(),
        topic=topic,
        beat=profile["beat"],
        voice=profile["voice"],
        experience=block("Experience the author may reference", "experience"),
        never=block("Hard rules — never do these", "never"),
        hashtags=block("Preferred hashtags", "hashtags"),
        used_urls="\n".join(f"- {u}" for u in used_urls[-60:]) or "- (none yet)",
        x_rules=X_RULES.format(max_len=MAX_TWEET_TEXT),
        linkedin_rules=LINKEDIN_RULES.format(max_len=MAX_LINKEDIN_TEXT),
    )


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def log_run(message: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")


def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except json.JSONDecodeError:
            print(f"WARNING: {HISTORY_FILE} is corrupt; starting fresh.",
                  file=sys.stderr)
    return []


def save_history(history: list) -> None:
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def log_drafts(item: dict, topic: str, x_post: str, li_post: str,
               posted_x: bool, posted_li: bool) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    entry = (
        f"\n---\n\n# {date.today().isoformat()} — {item['title']}\n\n"
        f"Topic: {topic}\n"
        f"Source: {item.get('source', 'n/a')}\n"
        f"Why: {item.get('why', 'n/a')}\n\n"
        f"## X{' (POSTED)' if posted_x else ''}\n\n{x_post}\n\n"
        f"## LinkedIn{' (POSTED)' if posted_li else ''}\n\n{li_post}\n"
    )
    with DRAFTS_FILE.open("a") as f:
        f.write(entry)


# ---------------------------------------------------------------------------
# API error translation
# ---------------------------------------------------------------------------

NOTHING_LOST = ("Nothing was saved, so today's topic is still available when "
                "you re-run.")


def friendly_api_error(exc: Exception) -> str:
    """Turn an Anthropic SDK exception into something worth reading.

    The raw exceptions are accurate but buried in a traceback; every case here
    has a specific thing the user should go do about it.
    """
    detail = str(exc)

    if isinstance(exc, anthropic.AuthenticationError):
        return (
            "Your Anthropic API key was rejected.\n\n"
            f"  Check the key in {ENV_FILE} — a real key is 100+ characters\n"
            "  and starts with 'sk-ant-'. The console only shows a masked\n"
            "  preview after creation, and pasting that masked value is the\n"
            "  usual cause. Create a fresh key and copy it from the dialog:\n"
            f"  {CONSOLE_KEYS}\n\n"
            "  Also check that a stale ANTHROPIC_API_KEY is not set in your\n"
            "  shell — an existing environment variable overrides the file.\n"
            "  Run 'unset ANTHROPIC_API_KEY' or open a new terminal."
        )

    if isinstance(exc, anthropic.PermissionDeniedError):
        return ("Your API key does not have permission for this request.\n\n"
                f"  Check the key's workspace and scopes: {CONSOLE_KEYS}")

    if isinstance(exc, anthropic.RateLimitError):
        return ("Rate limited by the Anthropic API.\n\n"
                "  Wait a minute and re-run. If this keeps happening, check\n"
                f"  your usage tier and limits: {CONSOLE_BILLING}\n\n"
                f"  {NOTHING_LOST}")

    if isinstance(exc, anthropic.BadRequestError):
        if "credit balance" in detail.lower():
            return (
                "Your Anthropic API credit balance is empty.\n\n"
                f"  Add credits here: {CONSOLE_BILLING}\n\n"
                "  API credits are prepaid and separate from any Claude\n"
                "  subscription. Each run costs a few cents, so a small\n"
                "  top-up lasts a long time. Setting a low-balance alert on\n"
                "  that page prevents the surprise next time.\n\n"
                f"  {NOTHING_LOST}"
            )
        return (f"The API rejected the request:\n\n  {detail}\n\n"
                "  This usually means the model name or a tool definition in\n"
                "  the script needs updating against current API docs.")

    if isinstance(exc, anthropic.APIConnectionError):
        return ("Could not reach the Anthropic API.\n\n"
                "  Check your network connection, then re-run. If you are on\n"
                "  a VPN or a corporate network, that is the first thing to\n"
                f"  rule out.\n\n  {NOTHING_LOST}")

    if isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, "status_code", "unknown")
        if status in (500, 502, 503, 529):
            return (f"The Anthropic API returned a server error ({status}).\n\n"
                    "  This is on their end, not yours. Wait a few minutes and\n"
                    f"  re-run.\n\n  {NOTHING_LOST}")
        return f"The Anthropic API returned an error ({status}):\n\n  {detail}"

    return f"Unexpected API error:\n\n  {detail}"


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

FIELD_PATTERN = re.compile(r"^===([A-Z]+)===\s*$", re.MULTILINE)


def parse_fields(text: str) -> dict:
    """Parse the delimited model response into a dict.

    Delimiters rather than JSON: post text routinely contains quotes,
    apostrophes, and line breaks, all of which need escaping inside a JSON
    string and break the parse whenever the model gets that wrong.
    """
    parts = FIELD_PATTERN.split(text)
    if len(parts) < 3:
        raise ValueError(
            f"Model output was not in the expected format:\n{text[:500]}")
    fields = {}
    for name, body in zip(parts[1::2], parts[2::2]):
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


def generate_item(client: anthropic.Anthropic, profile: dict, topic: str,
                  used_urls: list) -> dict:
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            messages=[{"role": "user",
                       "content": build_prompt(profile, topic, used_urls)}],
            tools=[{"type": "web_search_20250305", "name": "web_search",
                    "max_uses": 5}],
        )
    except anthropic.AnthropicError as exc:
        raise SystemExit(f"\n{friendly_api_error(exc)}\n") from None

    # Web-search responses contain several block types; keep only text blocks.
    text = "\n".join(b.text for b in response.content if b.type == "text")

    try:
        item = parse_fields(text)
    except ValueError as exc:
        raise SystemExit(
            f"\nThe model's response could not be parsed.\n\n  {exc}\n\n"
            f"  This is usually a one-off. Re-run and it will normally\n"
            f"  succeed.\n\n  {NOTHING_LOST}\n") from None

    missing = [k for k in ("url", "title", "tweet", "linkedin")
               if not item.get(k)]
    if missing:
        raise SystemExit(
            f"\nThe model's response was missing: {', '.join(missing)}.\n\n"
            f"  Re-run — this is usually a one-off.\n\n  {NOTHING_LOST}\n")

    if item["url"] in used_urls:
        raise SystemExit(
            f"\nThe model picked an item already covered:\n  {item['url']}\n\n"
            "  Re-run, or try a different topic — this one may be quiet this\n"
            f"  week.\n\n  {NOTHING_LOST}\n")

    # X gets hard-trimmed (the platform enforces the limit anyway). LinkedIn is
    # only flagged — trimming from the end would eat the closing question and
    # hashtags, which is worse than a draft you shorten by hand.
    item["tweet"] = trim(item["tweet"], MAX_TWEET_TEXT)
    item["linkedin"] = item["linkedin"].strip()
    if len(item["linkedin"]) > MAX_LINKEDIN_TEXT:
        print(f"WARNING: LinkedIn draft is {len(item['linkedin'])} characters "
              f"(ceiling {MAX_LINKEDIN_TEXT}) — shorten it before posting.",
              file=sys.stderr)
    return item


def compose_posts(item: dict) -> tuple:
    return f"{item['tweet']}\n{item['url']}", f"{item['linkedin']}\n\n{item['url']}"


# ---------------------------------------------------------------------------
# Optional publishing
# ---------------------------------------------------------------------------

def post_to_x(post: str) -> str:
    """Publish to X. Needs four user-context credentials; a Bearer token is
    app-only auth and cannot post."""
    try:
        import tweepy  # imported lazily so draft-only mode needs no dependency
    except ImportError:
        raise SystemExit("\n--post needs tweepy. Install it with:\n\n"
                         "  ~/.ai_post_venv/bin/pip install tweepy\n")

    creds = {k: os.environ.get(k) for k in
             ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")}
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise SystemExit(
            f"\n--post needs these in {ENV_FILE}: {', '.join(missing)}\n\n"
            "  These come from an X developer app set to Read and Write. A\n"
            "  Bearer token is app-only auth and cannot post on your behalf.\n")

    client = tweepy.Client(
        consumer_key=creds["X_API_KEY"],
        consumer_secret=creds["X_API_SECRET"],
        access_token=creds["X_ACCESS_TOKEN"],
        access_token_secret=creds["X_ACCESS_SECRET"],
    )
    try:
        return str(client.create_tweet(text=post).data.get("id", ""))
    except Exception as exc:
        raise SystemExit(
            f"\nX rejected the post:\n\n  {exc}\n\n"
            "  Common causes: the app is set to Read-only (change it, then\n"
            "  regenerate the access token — tokens keep the permissions they\n"
            "  were created with), or a duplicate post.\n"
            "  The drafts were not saved; re-run to try again.\n") from None


def post_to_linkedin(post: str) -> str:
    """Publish to LinkedIn via the REST Posts API.

    Optional and unused by the default workflow. Requires an approved LinkedIn
    app with the w_member_social scope, a member access token, and your author
    URN (urn:li:person:XXXX). LinkedIn revises both the API version header and
    its app-review requirements periodically — check current docs if this
    returns a 4xx.
    """
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    author = os.environ.get("LINKEDIN_AUTHOR_URN")
    if not token or not author:
        raise SystemExit(
            f"\n--post-linkedin needs LINKEDIN_ACCESS_TOKEN and "
            f"LINKEDIN_AUTHOR_URN in {ENV_FILE}.\n\n"
            "  Both come from an approved LinkedIn app with the\n"
            "  w_member_social scope.\n")

    payload = {
        "author": author,
        "commentary": post,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    request = urllib.request.Request(
        "https://api.linkedin.com/rest/posts",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": os.environ.get("LINKEDIN_API_VERSION", "202601"),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.headers.get("x-restli-id", "posted")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()[:300]
        raise SystemExit(
            f"\nLinkedIn rejected the post ({exc.code}):\n\n  {body}\n\n"
            "  LinkedIn revises its API version header on a schedule — if\n"
            "  this is a 4xx, check the current value and set\n"
            "  LINKEDIN_API_VERSION accordingly.\n") from None
    except urllib.error.URLError as exc:
        raise SystemExit(f"\nCould not reach LinkedIn: {exc.reason}\n") from None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Daily X and LinkedIn draft generator, driven by an "
                    "author profile file and a topic you pick at run time.")
    parser.add_argument("--topic",
                        help="menu number, part of a menu entry, or free text; "
                             "skips the interactive menu")
    parser.add_argument("--random-topic", action="store_true",
                        help="pick a topic from the menu at random")
    parser.add_argument("--list-topics", action="store_true",
                        help="show the topic menu and exit")
    parser.add_argument("--profile", type=Path, default=PROFILE_FILE,
                        help=f"author profile path (default: {PROFILE_FILE})")
    parser.add_argument("--post", action="store_true",
                        help="publish the X version instead of only drafting")
    parser.add_argument("--post-linkedin", action="store_true",
                        help="publish the LinkedIn version (needs an approved "
                             "LinkedIn app)")
    parser.add_argument("--history", action="store_true",
                        help="show the last 10 items used, then exit")
    args = parser.parse_args()

    load_env_file()

    if args.history:
        for h in load_history()[-10:]:
            topic = f"  [{h['topic']}]" if h.get("topic") else ""
            print(f"{h['date']}  {h['title'][:70]}{topic}\n            {h['url']}")
        return

    profile = load_profile(args.profile)
    topics = topic_menu(profile)

    if args.list_topics:
        for i, topic in enumerate(topics, 1):
            print(f"{i:>2}. {topic}")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            f"\nNo ANTHROPIC_API_KEY found (checked {ENV_FILE} and the "
            f"environment).\n\n  Create one at {CONSOLE_KEYS}, then:\n\n"
            f"    echo 'export ANTHROPIC_API_KEY=sk-ant-...' > {ENV_FILE}\n"
            f"    chmod 600 {ENV_FILE}\n")

    topic = choose_topic(topics, args.topic, args.random_topic)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    history = load_history()
    used_urls = [h["url"] for h in history]

    print(f"\nSearching: {topic}\n")
    item = generate_item(anthropic.Anthropic(), profile, topic, used_urls)
    x_post, li_post = compose_posts(item)

    tweet_id = post_to_x(x_post) if args.post else ""
    li_id = post_to_linkedin(li_post) if args.post_linkedin else ""

    history.append({
        "date": date.today().isoformat(),
        "topic": topic,
        "url": item["url"],
        "title": item["title"],
        "posted_x": bool(tweet_id),
        "posted_linkedin": bool(li_id),
        "tweet_id": tweet_id,
    })
    save_history(history)
    log_drafts(item, topic, x_post, li_post, bool(tweet_id), bool(li_id))
    log_run(f"OK — [{topic}] {item['title']} ({item['url']})")

    rule = "=" * 70
    print(rule)
    print("X — PUBLISHED" if tweet_id else "X — draft")
    print(rule)
    print(x_post)
    print(f"\n{rule}")
    print("LINKEDIN — PUBLISHED" if li_id else "LINKEDIN — draft")
    print(f"{rule}")
    print(li_post)
    print(f"\n[{len(item['linkedin'])} characters] Saved to {DRAFTS_FILE}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
    except SystemExit as exc:
        # Expected, explained failures: log the first line, print the message
        # as written, and exit without a traceback.
        if exc.code and isinstance(exc.code, str):
            log_run(f"FAILED — {exc.code.strip().splitlines()[0]}")
        raise
    except Exception as exc:
        # Genuinely unexpected: log it and let the traceback through, since
        # that is the useful artifact for an unknown bug.
        log_run(f"FAILED — {type(exc).__name__}: {exc}")
        raise
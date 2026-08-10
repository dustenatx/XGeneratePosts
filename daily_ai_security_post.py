#!/usr/bin/env python3
"""
daily_ai_security_post.py

Finds one noteworthy new item on a topic you define, then drafts two posts
from that same source:

  * X/Twitter — short, link-forward, hashtagged.
  * LinkedIn  — longer, first-person point of view on why the item matters.

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

MAX_TWEET_TEXT = 255       # 280 minus ~24 chars X reserves for a t.co link
MAX_LINKEDIN_TEXT = 1100   # hard ceiling; the prompt targets 750-950

# Profile sections. "required" ones must be present and non-empty.
PROFILE_SECTIONS = {
    "beat": True,        # what to look for each day
    "voice": True,       # how the author thinks and sounds
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
Today is {today}. Search the web for one genuinely noteworthy item matching the
author's beat below. Prefer the original vendor, author, or project page over a
news roundup or aggregator.

## The beat
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

Respond with ONLY a JSON object, no markdown fences, no commentary:
{{
  "url": "<canonical link to the item>",
  "title": "<item title>",
  "source": "<publisher/vendor>",
  "tweet": "<X post text WITHOUT the URL>",
  "linkedin": "<LinkedIn post text WITHOUT the URL>",
  "why": "<one sentence: why you picked it>"
}}
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


def build_prompt(profile: dict, used_urls: list) -> str:
    def block(title: str, key: str) -> str:
        body = profile.get(key, "").strip()
        return f"\n\n## {title}\n{body}" if body else ""

    return PROMPT.format(
        today=date.today().isoformat(),
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


def log_drafts(item: dict, x_post: str, li_post: str,
               posted_x: bool, posted_li: bool) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    entry = (
        f"\n---\n\n# {date.today().isoformat()} — {item['title']}\n\n"
        f"Source: {item.get('source', 'n/a')}\n"
        f"Why: {item.get('why', 'n/a')}\n\n"
        f"## X{' (POSTED)' if posted_x else ''}\n\n{x_post}\n\n"
        f"## LinkedIn{' (POSTED)' if posted_li else ''}\n\n{li_post}\n"
    )
    with DRAFTS_FILE.open("a") as f:
        f.write(entry)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def extract_json(text: str) -> dict:
    """Parse a JSON object out of model output, tolerating code fences."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output:\n{text[:500]}")
    return json.loads(match.group(0))


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


def generate_item(client: anthropic.Anthropic, profile: dict,
                  used_urls: list) -> dict:
    response = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": build_prompt(profile, used_urls)}],
        tools=[{"type": "web_search_20250305", "name": "web_search",
                "max_uses": 5}],
    )
    # Web-search responses contain several block types; keep only text blocks.
    text = "\n".join(b.text for b in response.content if b.type == "text")
    item = extract_json(text)

    for key in ("url", "title", "tweet", "linkedin"):
        if not item.get(key):
            raise ValueError(f"Model output missing '{key}': {item}")
    if item["url"] in used_urls:
        raise ValueError(f"Model reused an already-posted URL: {item['url']}")

    # X gets hard-trimmed (the limit is enforced by the platform). LinkedIn is
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
    import tweepy  # imported lazily so draft-only mode needs no dependency

    creds = {k: os.environ.get(k) for k in
             ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")}
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise SystemExit(f"--post requires: {', '.join(missing)}")

    client = tweepy.Client(
        consumer_key=creds["X_API_KEY"],
        consumer_secret=creds["X_API_SECRET"],
        access_token=creds["X_ACCESS_TOKEN"],
        access_token_secret=creds["X_ACCESS_SECRET"],
    )
    return str(client.create_tweet(text=post).data.get("id", ""))


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
        raise SystemExit("--post-linkedin requires LINKEDIN_ACCESS_TOKEN and "
                         "LINKEDIN_AUTHOR_URN")

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
        raise SystemExit(f"LinkedIn API error {exc.code}: {exc.read().decode()}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Daily X and LinkedIn draft generator, driven by an "
                    "author profile file.")
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
            print(f"{h['date']}  {h['title'][:70]}\n            {h['url']}")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(f"No ANTHROPIC_API_KEY found (checked {ENV_FILE} and "
                         "the environment).")

    profile = load_profile(args.profile)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    history = load_history()
    used_urls = [h["url"] for h in history]

    item = generate_item(anthropic.Anthropic(), profile, used_urls)
    x_post, li_post = compose_posts(item)

    tweet_id = post_to_x(x_post) if args.post else ""
    li_id = post_to_linkedin(li_post) if args.post_linkedin else ""

    history.append({
        "date": date.today().isoformat(),
        "url": item["url"],
        "title": item["title"],
        "posted_x": bool(tweet_id),
        "posted_linkedin": bool(li_id),
        "tweet_id": tweet_id,
    })
    save_history(history)
    log_drafts(item, x_post, li_post, bool(tweet_id), bool(li_id))
    log_run(f"OK — {item['title']} ({item['url']})")

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
    except Exception as exc:
        log_run(f"FAILED — {exc}")
        raise

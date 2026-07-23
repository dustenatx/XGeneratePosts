#!/usr/bin/env python3
"""
daily_ai_security_post.py

Once-daily pipeline:
  1. Uses the Claude API (with its built-in web search tool) to find one
     noteworthy NEW item about using AI to protect corporate environments
     (product, demo, article, research, tool release).
  2. Drafts an X/Twitter post in your voice with the link and hashtags.
  3. Default: saves the draft to drafts.md and prints it for review.
     With --post (and X API credentials set): publishes it directly.

Requirements:
    pip install anthropic tweepy

Environment variables:
    ANTHROPIC_API_KEY   required
    X_API_KEY           required only for --post
    X_API_SECRET        required only for --post
    X_ACCESS_TOKEN      required only for --post
    X_ACCESS_SECRET     required only for --post

Scheduling (run once a day) — see README.md.
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-6"          # docs: https://docs.claude.com/en/api/overview
DATA_DIR = Path.home() / "XPosts"
HISTORY_FILE = DATA_DIR / "history.json"   # URLs already used (dedup)
DRAFTS_FILE = DATA_DIR / "drafts.md"       # running log of generated posts
MAX_TWEET_TEXT = 255                       # 280 minus ~24 chars X reserves for a t.co link
LOG_FILE = DATA_DIR / "run.log"            # Make sure the run.log is not part of the repo

VOICE_GUIDELINES = """
Author profile (do not state these facts verbatim; use them to set tone):
- Senior engineering leader in cybersecurity, DevOps, and platform engineering; CISSP.
- Advocates practical adoption of AI in security programs while staying clear-eyed
  about misuse, model risk, and improper deployment.
- Writes for practitioners and security leaders: concrete, specific, no hype.

Hard rules for the post:
- NEVER mention career length, years of experience, or anything age-signaling.
- No breathless hype ("game-changer", "mind-blowing"). Lead with what the thing
  actually does and why a security team should care.
- Plain, confident, first-person-optional voice. One clear takeaway.
- 2-3 relevant hashtags (e.g. #CyberSecurity #AI #DevSecOps #InfoSec #BlueTeam),
  chosen to fit the item.
- Post text (excluding the URL) must be under {max_len} characters.
""".strip()

RESEARCH_PROMPT = """
Today is {today}. Search the web for something genuinely noteworthy published or
announced recently (ideally within the last 7 days) about using AI to improve the
protection of corporate environments. Acceptable: a new product or feature, a demo,
an article, a research paper, an open-source tool, or a talk. Focus on DEFENSE
(detection, response, hardening, GRC automation, SOC tooling) — not attacks.

Do NOT pick any of these already-used URLs:
{used_urls}

Pick exactly ONE item — the most substantive and interesting to security
practitioners and leaders. Then write an X/Twitter post about it.

{voice}

Respond with ONLY a JSON object, no markdown fences, no commentary:
{{
  "url": "<canonical link to the item>",
  "title": "<item title>",
  "source": "<publisher/vendor>",
  "tweet": "<post text WITHOUT the URL — the URL is appended separately>",
  "why": "<one sentence: why you picked it>"
}}
""".strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENV_FILE = Path.home() / ".ai_post_env"

def load_env_file(path: Path = ENV_FILE) -> None:
    """Load KEY=value lines (with or without 'export ') into os.environ."""
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

def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except json.JSONDecodeError:
            print(f"WARNING: {HISTORY_FILE} is corrupt; starting fresh.", file=sys.stderr)
    return []
def log_run(message: str) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")

def save_history(history: list[dict]) -> None:
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def extract_json(text: str) -> dict:
    """Parse a JSON object out of model output, tolerating code fences."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    # Grab the outermost {...} in case any stray text surrounds it.
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output:\n{text[:500]}")
    return json.loads(match.group(0))


def generate_item(client: anthropic.Anthropic, used_urls: list[str]) -> dict:
    prompt = RESEARCH_PROMPT.format(
        today=date.today().isoformat(),
        used_urls="\n".join(f"- {u}" for u in used_urls[-60:]) or "- (none yet)",
        voice=VOICE_GUIDELINES.format(max_len=MAX_TWEET_TEXT),
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
    )
    # Web-search responses contain multiple block types; keep only text blocks.
    text = "\n".join(b.text for b in response.content if b.type == "text")
    item = extract_json(text)

    for key in ("url", "title", "tweet"):
        if not item.get(key):
            raise ValueError(f"Model output missing '{key}': {item}")
    if item["url"] in used_urls:
        raise ValueError(f"Model reused an already-posted URL: {item['url']}")
    if len(item["tweet"]) > MAX_TWEET_TEXT:
        item["tweet"] = item["tweet"][: MAX_TWEET_TEXT - 1].rstrip() + "…"
    return item


def compose_post(item: dict) -> str:
    return f"{item['tweet']}\n{item['url']}"


def log_draft(item: dict, post: str, posted: bool) -> None:
    entry = (
        f"\n## {date.today().isoformat()} — {item['title']}"
        f" ({'POSTED' if posted else 'draft'})\n\n"
        f"{post}\n\n"
        f"Why: {item.get('why', 'n/a')}\n"
    )
    with DRAFTS_FILE.open("a") as f:
        f.write(entry)


def post_to_x(post: str) -> str:
    import tweepy  # imported lazily so review-only mode doesn't need it

    creds = {k: os.environ.get(k) for k in
             ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")}
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise SystemExit(f"--post requires env vars: {', '.join(missing)}")

    x = tweepy.Client(
        consumer_key=creds["X_API_KEY"],
        consumer_secret=creds["X_API_SECRET"],
        access_token=creds["X_ACCESS_TOKEN"],
        access_token_secret=creds["X_ACCESS_SECRET"],
    )
    result = x.create_tweet(text=post)
    return str(result.data.get("id", ""))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Daily AI-security X post generator")
    parser.add_argument("--post", action="store_true",
                        help="Publish to X instead of only saving a draft")
    args = parser.parse_args()

    load_env_file()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first.")

    client = anthropic.Anthropic()
    history = load_history()
    used_urls = [h["url"] for h in history]

    item = generate_item(client, used_urls)
    post = compose_post(item)

    posted = False
    tweet_id = ""
    if args.post:
        tweet_id = post_to_x(post)
        posted = True

    history.append({
        "date": date.today().isoformat(),
        "url": item["url"],
        "title": item["title"],
        "posted": posted,
        "tweet_id": tweet_id,
    })
    save_history(history)
    log_draft(item, post, posted)

    print(("PUBLISHED to X" if posted else "DRAFT saved to drafts.md") + "\n")
    print(post)
    log_run(f"OK — {item['title']} ({item['url']})")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_run(f"FAILED — {exc}")
        raise

# Daily Post Generator

Pick a technology topic, and this finds one noteworthy recent item on it and
drafts two social posts from that same source: a short one for X and a longer,
opinionated one for LinkedIn. Powered by the Claude API and its built-in web
search tool, so a single API key covers both the research and the writing.

Human-in-the-loop by default. Nothing is published unless you ask for it.

The posts sound like *you* because of a profile file you write once and keep
outside this repo. That file is the whole idea: the code is a small harness,
and the profile is where the topics, the voice, the point of view, and the
guardrails live.

## How it works

Each run:

1. Asks which topic to cover — a numbered menu from your profile's `## Topics`
   section, or a built-in catalog of common IT areas. `--topic` skips the
   prompt, `--random-topic` rolls the dice.
2. Searches the web for a substantive recent item in that area, filtered by
   your **beat**: what counts as a good find, what to exclude, who it is for.
3. Skips anything already used, tracked in `history.json`.
4. Writes two posts from that one source. The X version reports; the LinkedIn
   version argues — it takes a position, says what the item does not solve,
   and ends with a question worth answering.
5. Prints both drafts and appends them to `drafts.md` with the topic, source,
   and a one-line rationale for the pick.
6. Logs the outcome, success or failure, to `run.log`.

## Requirements

- Python 3.9+ (developed on 3.14)
- An Anthropic API key — https://console.anthropic.com
- `anthropic` (plus `tweepy` only if you use `--post`)

## Setup

**1. Virtual environment.** Required on Homebrew and modern-distro Pythons,
which block system-wide pip installs per PEP 668:

```bash
python3 -m venv ~/.ai_post_venv
~/.ai_post_venv/bin/pip install anthropic
```

**2. API key**, in a protected file outside the repo:

```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-your-full-key' > ~/.ai_post_env
chmod 600 ~/.ai_post_env
```

The script loads this at startup. An already-set environment variable wins,
which is handy for one-off overrides. The `export` prefix is optional but lets
the same file double as a shell-sourceable env file.

**3. Author profile — the important step.** Copy the scaffold to your data
directory and fill it in:

```bash
mkdir -p ~/XPosts
cp author_profile.example.md ~/XPosts/author_profile.md
```

The scaffold explains each section:

| Section | What it does |
|---|---|
| `## Topics` | Your run-time menu of technology areas. Omit it to use the built-in catalog |
| `## Beat` | What makes an item worth posting *whatever* the topic: quality bar, exclusions, audience |
| `## Voice` | How you think and sound — your actual positions, plus real sentences you wrote |
| `## Experience` | Things you have really done that posts may reference, with a guardrail capping it at one per post |
| `## Never` | Hard rules: no employer names, no invented hands-on claims, whatever would misrepresent you |
| `## Hashtags` | A pool to draw from |

Beat and Voice are required. Spend your time on **Voice** — and especially on
pasting a handful of sentences you actually wrote. A description of your tone
produces competent generic prose; real samples give the model a cadence to
imitate. **Never** is what keeps a model trying to sound expert from inventing
credentials on your behalf.

Keep this file out of version control — it is personal, and it is already in
`.gitignore`.

## Usage

```bash
~/.ai_post_venv/bin/python daily_post.py
```

You get a topic menu, then both drafts print to the terminal and land in
`~/XPosts/drafts.md`. Review, edit, post them yourself. Run whenever you like —
dedup makes irregular timing safe, and a second run the same day simply picks a
different item.

| Flag | Effect |
|---|---|
| *(none)* | Interactive topic menu, then draft both posts. The default |
| `--topic X` | Menu number, part of a menu entry, or free text not in the menu at all |
| `--random-topic` | Pick from the menu at random |
| `--list-topics` | Show the menu and exit |
| `--history` | Show the last 10 items used, with their topics |
| `--profile PATH` | Use a different profile file — handy for running more than one persona |
| `--post` | Publish the X version (see below) |
| `--post-linkedin` | Publish the LinkedIn version (see below) |

For a shorter daily command, keep a wrapper outside the repo, e.g.
`~/XPosts/aipost.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec "$HOME/.ai_post_venv/bin/python" "/path/to/daily_post.py" "$@"
```

`chmod +x` it once, then each day is `~/XPosts/aipost.sh` — and arguments pass
straight through, so `~/XPosts/aipost.sh --topic kubernetes` works too.

### Optional: publishing to X

```bash
~/.ai_post_venv/bin/pip install tweepy
python daily_post.py --post
```

Needs an X developer app set to **Read and Write** and four user-context
credentials in `~/.ai_post_env`. A Bearer token alone is app-only auth and
cannot post:

```bash
export X_API_KEY=...
export X_API_SECRET=...
export X_ACCESS_TOKEN=...
export X_ACCESS_SECRET=...
```

### Optional: publishing to LinkedIn

Included for anyone who wants it; the author of this repo drafts and posts
LinkedIn manually. Requires an approved LinkedIn app with the
`w_member_social` scope, a member access token, and your author URN:

```bash
export LINKEDIN_ACCESS_TOKEN=...
export LINKEDIN_AUTHOR_URN=urn:li:person:XXXXXXXX
# optional; LinkedIn revises this periodically
export LINKEDIN_API_VERSION=202601
```

LinkedIn's app review is meaningfully more involved than X's, and it changes
its API version header on a schedule. If `--post-linkedin` returns a 4xx,
check the current version header first.

### Optional: scheduling

Unattended runs need a topic, since there is no terminal to ask on — the script
says so rather than hanging:

```cron
0 8 * * * $HOME/.ai_post_venv/bin/python /path/to/daily_post.py --random-topic >> $HOME/XPosts/cron.log 2>&1
```

Env-file loading means no key handling in the crontab. On laptops that sleep,
`anacron` (Linux) or `launchd` (macOS) give "run once a day whenever awake"
semantics instead.

## Files

In the repo:

| File | Purpose |
|---|---|
| `daily_post.py` | The generator |
| `author_profile.example.md` | Scaffold to copy and fill in |

In your data directory (`~/XPosts` by default, override with
`AI_POST_DATA_DIR`):

| File | Purpose |
|---|---|
| `author_profile.md` | Your topics and voice. You write this; the script only reads it |
| `drafts.md` | Every draft generated, with date, topic, title, and rationale |
| `history.json` | URLs already used — dedup across runs |
| `run.log` | One timestamped line per run |

## Design notes

**Why the topic is chosen per run rather than fixed.** A single hardcoded
subject produces a monotonous feed and burns through the good material in that
niche fast. Picking per run lets one profile cover a whole professional range,
and `--random-topic` keeps it varied without a decision every morning.

**Why a profile file instead of constants in the script.** Voice, guardrails,
topics, and beat are the parts that differ per person and change most often.
Keeping them in plain text means you can edit your voice without touching code,
run several personas off one script with `--profile`, and share the code
without sharing anything personal.

**Why LinkedIn drafts are flagged rather than truncated.** X posts are
hard-trimmed at a sentence boundary because the platform enforces the limit
anyway. A LinkedIn post trimmed from the end loses its closing question and
hashtags — the two things you least want to lose — so an overlong draft prints
a warning and its character count, and you shorten it during review.

**Why the experience guardrail is worded so bluntly.** A model asked to write
as an experienced practitioner will produce plausible-sounding credentials it
was never given. Capping references at one per post and forbidding anything
outside the list is what keeps the output honest — and it matters more once
topics vary, since some days will land outside your deepest expertise.

## Security notes

- The API key lives in a `chmod 600` file in your home directory, never in the
  repo. `.gitignore` also excludes `.ai_post_env`, `*.env`, your profile, and
  all generated output.
- Before any public push: `grep -ri "sk-ant" .` should return nothing.
- If a key is ever committed, deleting it later does not scrub git history —
  rotate the key.

## License

MIT

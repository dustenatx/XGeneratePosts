# **AI Security Daily Post Generator**

A Python pipeline that finds one noteworthy new item each day about using AI to **defend corporate environments** — a product release, demo, article, research paper, or open-source tool — and drafts an X/Twitter post about it with the link and hashtags. Powered by the Claude API and its built-in web search tool, so a single API key covers both research and drafting.

Human-in-the-loop by default: the script generates a draft for you to review and post yourself. Automated posting via the X API is available but optional.

## **How it works**

Each run:

1. Searches the web for substantive, defense-focused AI-security content from roughly the last 7 days (detection, response, hardening, GRC automation, SOC tooling — not attacks).  
2. Skips anything already used, tracked in `history.json`.  
3. Drafts a post in a practitioner-focused voice with 2–3 relevant hashtags, sized to fit X's 280-character limit with the link.  
4. Prints the draft to the terminal and appends it to `drafts.md`, along with a one-line rationale for the pick.  
5. Logs the outcome (success or failure) with a timestamp to `run.log`.

## **Requirements**

* Python 3.9+ (tested on 3.14)  
* An Anthropic API key — https://console.anthropic.com  
* `anthropic` Python package (`tweepy` additionally, only if using `--post`)

## **Setup**

**1\. Create a virtual environment and install the dependency** (required on Homebrew/modern-distro Pythons, which block system-wide pip installs per PEP 668):

python3 \-m venv \~/.ai\_post\_venv  
\~/.ai\_post\_venv/bin/pip install anthropic

**2\. Store your API key** in a protected file in your home directory — outside the repo, so it can never be committed:

echo 'export ANTHROPIC\_API\_KEY=sk-ant-your-full-key' \> \~/.ai\_post\_env  
chmod 600 \~/.ai\_post\_env

The script loads this file automatically at startup (an already-set environment variable takes precedence, handy for one-off overrides). The `export` prefix is optional but lets the same file double as a shell-sourceable env file.

**3\. Output location.** Drafts, history, and the run log are written to `~/XPosts` (created automatically on first run), keeping generated content out of the repo. Change `DATA_DIR` at the top of the script to relocate.

## **Usage**

### **Manual run (default workflow)**

\~/.ai\_post\_venv/bin/python daily\_ai\_security\_post.py

The draft prints to the terminal and lands in `~/XPosts/drafts.md`; review, optionally tweak, and post it yourself. Run whenever you choose — dedup makes irregular timing safe, and running twice in a day simply yields a second, different item.

For a shorter command, a small wrapper script works well (kept outside the repo, e.g. `~/XPosts/aipost.sh`):

\#\!/usr/bin/env bash  
set \-euo pipefail  
exec "$HOME/.ai\_post\_venv/bin/python" "/path/to/daily\_ai\_security\_post.py" "$@"

`chmod +x` it once, then each day is just `~/XPosts/aipost.sh`.

### **Optional: automated posting**

With X API credentials, `--post` publishes directly instead of drafting:

\~/.ai\_post\_venv/bin/pip install tweepy  
python daily\_ai\_security\_post.py \--post

Requires an X developer app with **Read and Write** permissions and four user-context credentials added to `~/.ai_post_env` (a Bearer token alone is app-only auth and cannot post):

export X\_API\_KEY=...  
export X\_API\_SECRET=...  
export X\_ACCESS\_TOKEN=...  
export X\_ACCESS\_SECRET=...

### **Optional: scheduling with cron**

To run unattended once a day (machine must be awake at the scheduled time):

0 8 \* \* \* $HOME/.ai\_post\_venv/bin/python /path/to/daily\_ai\_security\_post.py \>\> $HOME/XPosts/cron.log 2\>&1

The built-in env-file loading means no key handling is needed in the crontab. On laptops that sleep, consider `anacron` (Linux) or `launchd` (macOS) for "run once a day whenever awake" semantics.

## **Generated files (in `~/XPosts`)**

| File | Purpose |
| ----- | ----- |
| `drafts.md` | Running log of every generated post with date, title, and rationale |
| `history.json` | URLs already used — dedup across runs |
| `run.log` | One timestamped line per run: success with the item picked, or the failure reason |

## **Tuning**

* **Voice and hard rules** (tone, hashtag pool, no-hype constraints): `VOICE_GUIDELINES` in the script.  
* **Topic focus and source preferences**: `RESEARCH_PROMPT` — e.g., add "prefer the original vendor/author page over news roundups" to bias toward primary sources.  
* **Model**: the `MODEL` constant (defaults to `claude-sonnet-4-6`).

## **Security notes**

* The API key lives in a `chmod 600` file in your home directory and is never stored in the repo; `.gitignore` also defensively excludes `.ai_post_env`, `*.env`, and generated output.  
* Before any public push: `grep -ri "sk-ant" .` in the repo folder should return nothing.  
* If a key is ever committed, removing it later does not scrub git history — rotate the key.

## **License**

MIT
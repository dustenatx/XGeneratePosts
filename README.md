# Daily AI-Security X Post — Setup

One Python script, one required API key. Runs once a day via cron or Task Scheduler.

## 1. Install

```bash
pip install anthropic tweepy
```

## 2. Keys

| Variable | Needed for | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | always (search + drafting) | https://console.anthropic.com |
| `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` | only `--post` (auto-publish) | https://developer.x.com — create an app with **Read and Write** permissions |

The script uses Claude's built-in web search tool, so no separate search API is needed.

## 3. Try it

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python daily_ai_security_post.py          # generates a draft, saves to drafts.md
python daily_ai_security_post.py --post   # generates AND publishes to X
```

Files created next to the script:
- `drafts.md` — running log of every generated post
- `history.json` — URLs already used, so the same item is never picked twice

## 4. Schedule once a day

**Linux / macOS (cron):** `crontab -e`, then (8:00 AM daily):

```cron
0 8 * * * ANTHROPIC_API_KEY=sk-ant-... /usr/bin/python3 /path/to/daily_ai_security_post.py >> /path/to/run.log 2>&1
```

Add the X_* variables and `--post` when you're ready for auto-publish.

**Windows (Task Scheduler):**

```powershell
schtasks /create /tn "DailyAISecurityPost" /tr "python C:\path\daily_ai_security_post.py" /sc daily /st 08:00
```

Set the environment variables under System Properties → Environment Variables (user scope is fine).

## 5. Recommended rollout

Run in draft mode for the first week and review `drafts.md` each morning. When you're happy with the voice, switch the scheduled command to `--post`.

## Tuning

- Voice/tone rules live in `VOICE_GUIDELINES` in the script (already excludes any career-length or age-signaling references).
- Hashtag pool and defense-only focus live in `RESEARCH_PROMPT`.
- Post time = whatever time you schedule; the script itself has no clock logic.

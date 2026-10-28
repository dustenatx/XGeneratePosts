# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub: on the repository's
**Security** tab, choose **Report a vulnerability**. Don't open a public
issue for a security problem.

Include what you found, the steps to reproduce it, and the commit you
tested. This is a one-person project, so replies may take a few days.

## Scope

XGeneratePosts runs locally from the command line and has no hosted service.
Issues of particular interest:
- key handling: API keys and tokens are read from `~/.ai_post_env` and the
  environment (`xgenerateposts/config.py`) and must never be printed,
  including in error messages;
- what the author profile and topic send to the AI provider
  (`xgenerateposts/prompt.py`, `xgenerateposts/providers.py`);
- fetching feeds and following redirects (`xgenerateposts/net.py`,
  `xgenerateposts/feeds.py`), including the refusal to follow an HTTPS
  redirect to plain HTTP;
- the draft-only default: nothing is posted to X or LinkedIn without an
  explicit `--post` or `--post-linkedin` flag;
- `xgp init`: the profile it creates in `~/XPosts` gets file mode 600, and an
  existing profile is never overwritten.

## Supported versions

Only the latest commit on `master` is supported. There are no tagged
releases yet.

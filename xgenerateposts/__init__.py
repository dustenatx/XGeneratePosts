"""
XGeneratePosts

Picks a technology topic, finds one noteworthy recent item on it, and drafts
two posts from that same source:

  * X/Twitter — short, link-forward, hashtagged.
  * LinkedIn  — longer, first-person point of view on why the item matters.

The topic is chosen at run time: pass --topic, or answer the numbered menu.
The menu comes from the '## Topics' section of your author profile if you
have one, otherwise from TOPIC_CATALOG below.

What makes the posts sound like YOU is an author profile file kept outside
this repo (default: ~/XPosts/author_profile.md). `xgp init` copies the
scaffold, author_profile.example.md in this package, there to fill in.

Default behavior is draft-only: both posts are printed and appended to
drafts.md for you to review and post yourself. Optional flags can publish to
X (--post) or LinkedIn (--post-linkedin).

The model comes from one of three providers (--provider, default groq):

  * groq           — free tier; the standard library is enough.
  * openai-compat  — any OpenAI-compatible endpoint (Gemini, Cerebras, Ollama).
  * anthropic      — paid; needs the anthropic package.

Requirements:
    Python standard library only for groq and openai-compat.
    The 'anthropic' extra        (only for --provider anthropic)
    The 'x' extra, tweepy        (only for --post)
    Installed xgp, from the clone:  uv tool install --reinstall '.[anthropic]'
    The clone's venv:               ~/.ai_post_venv/bin/pip install -e '.[anthropic]'
    The pinned versions are in pyproject.toml.

Credentials are read from ~/.ai_post_env — see README.md.
"""

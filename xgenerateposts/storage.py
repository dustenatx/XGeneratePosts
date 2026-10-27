"""Files: the author profile, and the history, drafts and run log in the data
directory."""

import json
import sys
from datetime import date, datetime
from pathlib import Path

from xgenerateposts import config
from xgenerateposts.author_profile import parse_profile

RUN_VIA = ""  # "provider/model, search source" once main() has chosen them (R13)


def log_run(message: str) -> None:
    config.data_dir().mkdir(parents=True, exist_ok=True)
    via = f" [via {RUN_VIA}]" if RUN_VIA else ""
    with config.log_file().open("a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {message}{via}\n")


def warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)
    log_run(f"WARNING — {message}")


def load_profile(path: Path) -> dict:
    """Read and parse the author profile (see author_profile.parse_profile)."""
    if not path.exists():
        raise SystemExit(
            f"No author profile at {path}\n"
            "Copy author_profile.example.md from the repo to that path and "
            "fill it in — it is what makes the posts sound like you."
        )
    return parse_profile(path.read_text(), path)


def load_history() -> list:
    history_file = config.history_file()
    if history_file.exists():
        try:
            return json.loads(history_file.read_text())
        except json.JSONDecodeError:
            print(f"WARNING: {history_file} is corrupt; starting fresh.", file=sys.stderr)
    return []


def save_history(history: list) -> None:
    config.history_file().write_text(json.dumps(history, indent=2))


def log_drafts(
    item: dict,
    topic: str,
    x_post: str,
    li_post: str,
    posted_x: bool,
    posted_li: bool,
    via: str = "",
) -> None:
    config.data_dir().mkdir(parents=True, exist_ok=True)
    entry = (
        f"\n---\n\n# {date.today().isoformat()} — {item['title']}\n\n"
        f"Topic: {topic}\n"
        f"Via: {via or 'n/a'}\n"
        f"Source: {item.get('source', 'n/a')}\n"
        f"Why: {item.get('why', 'n/a')}\n\n"
        f"## X{' (POSTED)' if posted_x else ''}\n\n{x_post}\n\n"
        f"## LinkedIn{' (POSTED)' if posted_li else ''}\n\n{li_post}\n"
    )
    with config.drafts_file().open("a") as f:
        f.write(entry)

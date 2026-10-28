#!/usr/bin/env bash
# R42: build the package, install the wheel into a fresh virtual environment
# with a throwaway HOME and data directory, and check xgp --help and xgp init.
set -euo pipefail

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

rm -rf dist
uv build
uv venv --quiet "$tmp/venv"
uv pip install --quiet --python "$tmp/venv/bin/python" dist/*.whl

export HOME="$tmp/home" AI_POST_DATA_DIR="$tmp/data"
mkdir "$HOME"
xgp="$tmp/venv/bin/xgp"
python="$tmp/venv/bin/python"
profile="$AI_POST_DATA_DIR/author_profile.md"

# R49: the wheel's METADATA declares each extra in pyproject.toml with its exact
# pin. This reads the metadata only; the extras are not installed.
"$python" - dist/*.whl <<'EOF'
import sys, tomllib, zipfile

extras = tomllib.load(open("pyproject.toml", "rb"))["project"]["optional-dependencies"]
with zipfile.ZipFile(sys.argv[1]) as wheel:
    metadata = next(n for n in wheel.namelist() if n.endswith(".dist-info/METADATA"))
    lines = wheel.read(metadata).decode().splitlines()
for extra, requirements in extras.items():
    expected = [f"Provides-Extra: {extra}"]
    expected += [f"Requires-Dist: {r} ; extra == '{extra}'" for r in requirements]
    for line in expected:
        if line not in lines:
            sys.exit(f"::error::wheel METADATA lacks: {line}")
        print(line)
EOF

# Mode as an octal string, plus the file's sha256 when it is a file.
inspect() {
  "$python" -c '
import hashlib, os, stat, sys
path = sys.argv[1]
mode = oct(stat.S_IMODE(os.stat(path).st_mode))
digest = hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.isfile(path) else ""
print(mode, digest)
' "$1"
}

"$xgp" --help
"$xgp" init

read -r dir_mode _ <<<"$(inspect "$AI_POST_DATA_DIR")"
echo "data directory mode: $dir_mode"
[ "$dir_mode" = 0o700 ] || { echo "::error::new data directory mode is $dir_mode, not 0o700"; exit 1; }

before=$(inspect "$profile")
echo "profile mode and sha256: $before"
[ "${before%% *}" = 0o600 ] || { echo "::error::profile mode is ${before%% *}, not 0o600"; exit 1; }

if "$xgp" init; then
  echo "::error::a second xgp init succeeded"
  exit 1
fi
[ "$(inspect "$profile")" = "$before" ] || { echo "::error::a second xgp init changed the profile"; exit 1; }

echo "Install check passed."

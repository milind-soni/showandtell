#!/bin/sh
# Desktop-launched Codex may not inherit the terminal's Homebrew PATH.
# Homebrew's python3 is always new enough, so it is tried before PATH's,
# which can be the older system interpreter; the script checks the version.
set -eu
PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
export PATH
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        # This runtime uses only stdlib; skip unrelated site startup hooks.
        exec "$candidate" -S "$script_dir/showandtell.py" "$@"
    fi
done
printf '%s\n' 'Showandtell needs Python 3.10+. Run its installer or: brew install python ffmpeg' >&2
exit 1

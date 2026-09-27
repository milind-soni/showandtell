#!/bin/sh
# Desktop-launched Codex may not inherit the terminal's Homebrew PATH.
set -eu
PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
export PATH
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for candidate in python3 "/opt/homebrew/bin/python3" "/usr/local/bin/python3"; do
    if "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
        exec "$candidate" "$script_dir/showandtell.py" "$@"
    fi
done
printf '%s\n' 'Showandtell needs Python 3.10+. Run its installer or: brew install python ffmpeg' >&2
exit 1

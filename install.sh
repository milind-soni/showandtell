#!/bin/sh
# Install the public Showandtell plugin. Safe to run again for an update.
set -eu

fail() { printf 'Showandtell: %s\n' "$*" >&2; exit 1; }
[ "$(uname -s)" = Darwin ] || fail 'This installer supports macOS. See README.md for manual installation.'
PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
export PATH

install_with_brew() {
    command -v brew >/dev/null 2>&1 || fail 'Install the missing prerequisites with Homebrew (https://brew.sh), then rerun this installer. Required: Codex CLI, Python 3.10+, FFmpeg.'
    printf 'Installing with Homebrew: %s\n' "$*"
    brew install "$@" || fail "Homebrew could not install $*. Fix the error above and rerun."
    hash -r
}

find_python() {
    for candidate in python3 "/opt/homebrew/bin/python3" "/usr/local/bin/python3"; do
        if "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
            showandtell_python=$candidate
            return 0
        fi
    done
    return 1
}

command -v codex >/dev/null 2>&1 || install_with_brew --cask codex
codex plugin marketplace add --help >/dev/null 2>&1 && codex plugin add --help >/dev/null 2>&1 || fail 'Update Codex CLI to a version with plugin commands, then rerun.'
if ! find_python; then
    install_with_brew python
    find_python || fail 'Python 3.10+ is still unavailable. Check your Homebrew installation.'
fi
if ! ffmpeg -version >/dev/null 2>&1 || ! ffprobe -version >/dev/null 2>&1; then
    install_with_brew ffmpeg
    ffmpeg -version >/dev/null 2>&1 && ffprobe -version >/dev/null 2>&1 || fail 'FFmpeg/FFprobe are still unavailable. Check your Homebrew installation.'
fi

# Never replace an unrelated marketplace with the same name.
marketplaces=$(codex plugin marketplace list --json) || fail 'Could not read Codex marketplaces.'
source_kind=$(printf '%s\n' "$marketplaces" | "$showandtell_python" -c '
import json, sys
matches = [m for m in json.load(sys.stdin)["marketplaces"] if m.get("name") == "showandtell"]
if not matches:
    print("missing")
else:
    source = matches[0].get("marketplaceSource", {})
    url = source.get("source", "").rstrip("/").removesuffix(".git")
    print("git" if source.get("sourceType") == "git" and url in (
        "https://github.com/milind-soni/showandtell", "milind-soni/showandtell",
        "git@github.com:milind-soni/showandtell") else "other")
') || fail 'Could not understand Codex marketplace information. Update Codex CLI and retry.'
case "$source_kind" in
    missing) codex plugin marketplace add milind-soni/showandtell ;;
    git) codex plugin marketplace upgrade showandtell ;;
    *) fail 'A different or local marketplace named showandtell already exists. Keep using that installation, or remove it with: codex plugin marketplace remove showandtell' ;;
esac
codex plugin add showandtell@showandtell

printf '\n%s\n' 'Showandtell is installed.' \
    'Open a new Codex chat, run /hooks, and review and enable the Showandtell hooks.' \
    'Hook trust is required; this installer does not grant it.' \
    'Then ask: Use Showandtell to make a video of this walkthrough.' \
    'Videos are saved in ~/.showandtell/.'

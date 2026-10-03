#!/bin/sh
# Install the public Showandtell plugin. Safe to run again for an update.
set -eu

fail() { printf 'Showandtell: %s\n' "$*" >&2; exit 1; }
showandtell_install_claude=false
case "$#" in
    0) ;;
    1) [ "$1" = --claude ] || fail 'Usage: install.sh [--claude]'; showandtell_install_claude=true ;;
    *) fail 'Usage: install.sh [--claude]' ;;
esac
[ "$(uname -s)" = Darwin ] || fail 'This installer supports macOS. See README.md for manual installation.'
PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
export PATH
[ "$showandtell_install_claude" = false ] || command -v claude >/dev/null 2>&1 || fail 'Install Claude Code first (https://code.claude.com/docs/en/setup), then rerun with --claude.'

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

if [ "$showandtell_install_claude" = true ]; then
    installed_plugins=$(codex plugin list --marketplace showandtell --json) || fail 'Could not locate the installed Showandtell plugin.'
    showandtell_plugin_root=$(printf '%s\n' "$installed_plugins" | "$showandtell_python" -c '
import json, os, re, sys
from pathlib import Path
matches = [p for p in json.load(sys.stdin)["installed"]
           if p.get("pluginId") == "showandtell@showandtell" and p.get("installed") is True]
if len(matches) != 1:
    sys.exit("Expected one installed Showandtell plugin. Run codex plugin list --marketplace showandtell --json to inspect it.")
version = matches[0].get("version")
if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", version):
    sys.exit("The installed Showandtell version is invalid.")
codex_home = Path(os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")).expanduser()
root = codex_home / "plugins/cache/showandtell/showandtell" / version
manifest = root / "plugin.json"
if not manifest.is_file():
    manifest = root / ".codex-plugin/plugin.json"
metadata = json.loads(manifest.read_text())
if metadata.get("name") != "showandtell" or metadata.get("version") != version or not (root / "scripts/run.sh").is_file():
    sys.exit("The installed Showandtell runtime is incomplete. Reinstall the plugin and retry.")
print(root.resolve())
') || fail 'Could not find a complete Showandtell runtime in the Codex plugin cache. Update Codex CLI and retry.'
    /bin/sh "$showandtell_plugin_root/scripts/run.sh" claude-setup --install || fail 'Claude setup failed. Fix the error above and rerun with --claude.'
fi

printf '\n%s\n' 'Showandtell is installed.' \
    'Open a new Codex chat, run /hooks, and review and enable the Showandtell hooks.' \
    'Hook trust is required; this installer does not grant it.' \
    'Then ask: Use Showandtell to make a video of this walkthrough.' \
    'Videos are saved in ~/.showandtell/.'
[ "$showandtell_install_claude" = false ] || printf '%s\n' 'Claude Code is configured too. Start a new session to use codex-cu and Showandtell.'

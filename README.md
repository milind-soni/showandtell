# showandtell

Turn Codex computer use into a video. Real screenshots, smooth animated cursor, local MP4. No screen-recording process, web service, account, or editor.

[Watch the real browser demo](demo/showandtell.mp4)

![Showandtell video preview](demo/preview.png)

## Install

Requires a current Codex with command hooks and unified computer use, **Python 3.10+**, and **FFmpeg**. Tested on macOS with Codex CLI 0.153.4. Linux export is supported; Windows capture is not supported in this release.

```sh
brew install python ffmpeg # only if missing
codex plugin marketplace add milind-soni/showandtell
codex plugin add showandtell@showandtell
```

Open a new Codex chat, review Showandtell's hooks using `/hooks`, and enable them. Installing a plugin does **not** grant hook trust. Then ask: **“Use Showandtell to make a video of this walkthrough.”**

Once enabled, hooks capture supported computer-use actions in every chat where the plugin is active and export after each turn. Videos appear in `~/.showandtell/<session>/<turn>/video.mp4`. Disable the plugin to stop capturing. No recording is uploaded.

## What happens

1. `PreToolUse` adds a small recorder to `cua_repl.js` after its required discovery call.
2. The recorder wraps public app/tab methods and emits screenshots before and after each action, plus action times and available coordinates.
3. `PostToolUse` saves those results. `Stop` renders 1280×800 H.264 at 60 fps with eased cursor travel, click ripples, drag motion, and shortened idle pauses.

Export is headless. Capture uses Codex's existing app/browser access; native applications still need a running desktop. The live demo used a hidden Codex browser tab, six screenshots, and three clicks. No continuous display recording was used.

**Hook permission behavior:** Codex currently requires `permissionDecision: "allow"` with `updatedInput` to rewrite a tool call. Showandtell uses this only for the exact CUA JavaScript tool name. Review this behavior before trusting the hook; it is not a passive observer. It does not install a PermissionRequest hook or edit trust settings. See [Codex hooks](https://learn.chatgpt.com/docs/hooks) and [plugin packaging](https://developers.openai.com/plugins/build/plugins).

## Current limits

- **Coordinate clicks and drags:** full animated cursor. Accessibility-index actions: screenshots and state changes, but no invented cursor position. The public API does not reveal their resolved targets.
- **Snapshots, not live footage:** page animation, scroll transitions, and per-character typing between snapshots are not preserved. Cursor movement is reconstructed, not the original ghost cursor's exact trajectory.
- Use unified `cua` app/tab methods and mutable `let`/`var` handles. First discovery remains untouched. Initial `const` handles on immutable targets can miss capture; the bundled skill explains recovery. Older browser-only tools and direct Playwright calls are not instrumented.
- Native screenshots may already contain Codex's ghost cursor. Showandtell cannot reliably remove it, so native videos can show duplicate cursors. The tested browser screenshots are clean.
- Keep unrelated image emissions out of an action call. Codex groups text and images separately; a mismatched image/marker count is reported and cursor association is withheld.
- Screenshots are emitted through the tool result, adding capture time and image tokens. Long turns take longer to render; interrupted exports can be rerun.
- Saved transcripts can truncate image output, especially large native screenshots. Import cannot reconstruct missing image data; recovery may produce an incomplete video or no video.
- Hook handlers and a real capture/export were tested separately. The normal user-trusted hook dispatcher must be enabled in your installation; this project does not silently grant that trust.
- The Blender native test exported nine UI actions and 18 screenshots into a 29.65-second, 60 fps video using a temporary local sidecar because transcript images were truncated. This does not verify automatic native capture/export through the hook dispatcher.

## Local tools

From a clone:

```sh
python3 plugins/showandtell/scripts/showandtell.py doctor
python3 plugins/showandtell/scripts/showandtell.py render /path/to/capture
python3 plugins/showandtell/scripts/showandtell.py import /path/to/rollout.jsonl -o /path/to/capture
```

The importer reads saved CUA/browser MCP results without executing their code. It cannot recover omitted frames or pointer paths. `session.json` is the portable screenshot/action manifest; `export.json` contains warnings. `SHOWANDTELL_HOME` changes the storage directory; `SHOWANDTELL_DISABLED=1` makes hooks do nothing (set in the environment launching Codex).

Marker logs omit typed text, keys, URLs, and raw tool code. **Screenshots still contain whatever is visible.** Captures remain on disk until you remove them. Review videos before sharing.

## Development

No Python packages or Node packages are required. Node is only needed for the capture-helper checks.

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/test_render.py
node --test tests/test_capture.mjs
python3 -m http.server 8768 --bind 127.0.0.1 --directory demo
```

Open `http://127.0.0.1:8768` through Codex computer use for the disposable live fixture. Click Calm, Bold, and Create walkthrough. The renderer check generates a real MP4, inspects it with FFprobe, and checks chronology, cursor endpoints, frame bounds, and atomic failure recovery.

For local installation, use `codex plugin marketplace add /absolute/path/to/showandtell`, then the same plugin-add command above. Packaging lives in `.agents/plugins/marketplace.json` and `plugins/showandtell/`.

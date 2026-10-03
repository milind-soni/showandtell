# showandtell

Turn Codex computer use into a local video. Showandtell keeps the screenshots the computer-use engine already takes, including the ones behind text-only accessibility observations, adds a smooth animated cursor, and renders an MP4 in the background. No screen recorder, recording server, account, or editor.

[Install](#install) · [Claude Code](#claude-code-experimental) · [Performance](#performance) · [Download v0.5.0](https://github.com/milind-soni/showandtell/releases/tag/v0.5.0)

[Watch the browser demo](demo/showandtell.mp4)

![Showandtell preview](demo/preview.png)

## Install

Requires current Codex desktop computer use and command hooks, **Python 3.10+**, and **FFmpeg**. Tested on macOS. Exporting saved captures also works on Linux; Windows capture is not supported.

**1. Install on your Mac:**

```sh
curl -fsSL https://raw.githubusercontent.com/milind-soni/showandtell/main/install.sh | sh
```

The installer checks Codex CLI, Python, and FFmpeg, uses your existing [Homebrew](https://brew.sh) for missing prerequisites, and installs this GitHub plugin. If everything is present, Homebrew is unnecessary. You can [inspect the installer](install.sh) first. It does not install Homebrew or grant hook trust.

**2. Review and enable Showandtell's hooks** in Codex (`/hooks` in the CLI). Installing a plugin does not grant hook trust. See [OpenAI's hook setup](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks).

**3. Start a new desktop chat and ask:**

> Use Showandtell to make a video of this walkthrough.

Once enabled, supported computer-use calls are recorded automatically in chats where the plugin is active. After each turn, a short-lived local job renders `~/.showandtell/<session>/<turn>/video.mp4`. It can finish after the chat process exits. Capture files stay on your computer until you delete them.

### Try it

> Use Showandtell to record a short walkthrough of https://github.com/milind-soni/showandtell. Browse the README, open Releases, and go back. Use coordinate clicks for smooth cursor animation. Verify that screenshots were saved, then give me the MP4.

Let the turn finish to queue automatic export. On your next message, ask **“Show me the latest Showandtell video from this chat.”**

### Claude Code (experimental)

Showandtell includes a Claude hook adapter for the **bundled local Codex computer-use MCP**, registered as `codex-cu`. The launch, hook dispatch, and recorder injection are verified. Recording is not: when Claude launches the engine, the engine runs REPL code without Codex turn metadata and therefore read-only, so the recorder cannot save frames and reports `capture-storage-unavailable`. Until that changes, treat the Claude route as a way to drive the engine, not to record it.

```sh
curl -fsSL https://raw.githubusercontent.com/milind-soni/showandtell/main/install.sh | sh -s -- --claude
```

This installs the Codex plugin, discovers the newest installed computer-use configuration, registers its command/arguments/environment with Claude, and adds Showandtell's hooks and skill. Existing unrelated settings are preserved, a changed settings file is backed up, and conflicting MCP configurations are refused. Repeating setup updates Showandtell's own installation. Tool permissions are not auto-approved.

Native apps need a running, logged-in Mac desktop, the installed app backend, and app consent accepted by that client. Browser calls on the tested bundled backend require Codex `session_id`/`turn_id` metadata that a Claude run does not have; use Codex for browser capture. This is unofficial reuse of the bundled MCP, not a standalone public computer-use API, and app updates can break it.

To test without changing Claude user settings, from a clone:

```sh
sh plugins/showandtell/scripts/run.sh claude-setup --output /private/path/to/config
claude -p 'Use codex-cu to calculate 12 × 12 in Calculator with screenshot observations.' \
  --strict-mcp-config --mcp-config /private/path/to/config/mcp.json \
  --settings /private/path/to/config/settings.json --allowedTools 'mcp__codex-cu__js'
```

The generated files contain local runtime configuration and should stay private. Claude captures are namespaced under `~/.showandtell/claude-<session>/<turn>/`, and the recorder runtime is copied into `~/.showandtell/runtime`. See [Claude hooks](https://code.claude.com/docs/en/hooks) and [MCP setup](https://code.claude.com/docs/en/mcp).

### Manual installation

```sh
brew install --cask codex # if missing
brew install python ffmpeg # if missing
codex plugin marketplace add milind-soni/showandtell
codex plugin add showandtell@showandtell
```

For optional Claude setup from a clone:

```sh
sh plugins/showandtell/scripts/run.sh claude-setup --install
```

No Python or npm packages, Showandtell API key, or remote recording server are needed.

### Update or uninstall

Finish active recordings before updating, rerun the installer, review changed hooks, and start a **new chat**. For Claude, rerun with `--claude` and restart Claude Code. A GitHub-backed Codex installation can also update with:

```sh
codex plugin marketplace upgrade showandtell
codex plugin add showandtell@showandtell
```

Remove the Codex plugin with `codex plugin remove showandtell@showandtell`. For Claude, remove Showandtell's hook entries from `~/.claude/settings.json`, remove its skill directory `~/.claude/skills/showandtell`, and remove the server with `claude mcp remove --scope user codex-cu` if you no longer use it. Settings backups and captures are retained until you delete them. `SHOWANDTELL_DISABLED=1` in the environment launching the agent temporarily disables capture and automatic export.

### Troubleshooting

| Problem | What to do |
| --- | --- |
| Missing prerequisites | Install with [Homebrew](https://brew.sh), then rerun the installer. |
| Codex does not recognize `plugin` | Update Codex CLI; the installer needs plugin commands. |
| An existing local marketplace is named `showandtell` | Update that local source and reinstall with `codex plugin add showandtell@showandtell`. The public installer does not replace it. |
| No video | Check hook enablement, start a new chat, and use unified computer use. Shell, API, and text-only browser actions have no video frames. |
| Hook points to a missing old version | Start a new chat or restart the agent to load current hooks. |
| Clicks appear twice in `session.json` | An older recorder from a long-running chat wrapped the new one. Start a new chat after upgrading. |
| `capture-storage-unavailable` with `code: EPERM` | The engine ran the recorder read-only. This is the normal state outside Codex (see the Claude section); inside Codex, check the thread's sandbox settings. |
| Claude cannot find the Mac runtime | Open/update Codex desktop with computer use installed, then rerun Claude setup. |
| Export is queued or failed | Use `status`; inspect `export.json` and private `export.log`, then retry with `export <capture-directory>`. |

## What happens

1. `PreToolUse` adds the recorder to the supported JavaScript MCP call after its required first discovery call. It also collects the previous call's recording; there is no per-call post hook.
2. The recorder instruments the app and tab handles the agent uses. For Mac apps, every observation already makes the engine take a screenshot; `getScreenshot` and `getAXStateAndScreenshot` return it, and for `getAXState` the recorder makes the same public engine call itself so that image becomes a frame instead of being discarded. Default `actions` mode also saves the screen after each action, so batched actions keep every state.
3. Stop collects the remainder and starts a detached export job with disconnected input/output.
4. FFmpeg renders 1280×800 H.264 at 60 fps with eased cursor travel, click ripples, drag motion, and shortened idle pauses. Per-turn locking and capture digests avoid duplicate rendering; a successful export atomically replaces the previous video.

There is no continuously running Showandtell daemon. The capture and encoder use local CPU and disk. `status` returns without waiting for rendering and reports queued, rendering, ready, error, or no-frames. Saved captures can be exported again if the machine shuts down or an export fails.

**Codex hook permission behavior:** Codex requires `permissionDecision: "allow"` with `updatedInput` to rewrite a tool call. Showandtell uses this only for the exact CUA JavaScript tool name. Review that behavior before trusting the hook; it is not a passive observer. Claude supports input rewriting without this permission decision, so its adapter omits it. Showandtell does not install a PermissionRequest hook or edit approval settings. See [Codex hooks](https://learn.chatgpt.com/docs/hooks).

**AX diff note:** after Showandtell's own screenshot of an app, the agent's next `getAXState` on that app returns a full accessibility tree instead of a diff. The engine's diff baseline moved, so a diff would wrongly say "no change"; the full tree costs more tokens once per action batch but stays correct.

## Performance

**Lightweight does not mean zero overhead.** Per computer-use call there is one hook process before the call (none after), a small JavaScript prelude that is parsed but not re-executed, and small local writes awaited inside the call so frames survive its end. Export starts separately, so the turn does not wait for FFmpeg; rendering still consumes CPU and disk.

| Measurement | 0.4.0 | 0.5.0 | Scope |
| --- | --- | --- | --- |
| Hook process per call | 2 × ~130–150 ms | 1 × ~28 ms | Pre + Post before; Pre only now. Apple M5, load average 5; Python 3.14 startup is ~10 ms of it. |
| Frame for a Mac `getAXState` | not captured | 0 extra engine calls | The engine already took it; the recorder keeps the file it returns. |
| Frame after each action (`actions` mode) | 1 engine observation | 1 engine observation | 100–700 ms each on Calculator, including the engine's UI-settle wait. |
| Export a saved 13.35-second video | 1.72 s median | unchanged | 1280×800 at 60 fps. |

These are component measurements, **not an end-to-end benchmark or speed guarantee**. App load, resolution, disk speed, and recording length change the result. Captures consume disk space until removed.

`SHOWANDTELL_CAPTURE=reuse` in the environment launching Codex requests nothing extra and still keeps every Mac observation's screenshot; `SHOWANDTELL_CAPTURE=full` adds screenshots before and after every action. Start a fresh chat after changing the mode.

## Using it with GitHub

- Install/update directly from this repository; plugin directory approval is unnecessary for this route.
- Record browser walkthroughs of GitHub or demonstrate a local app for a PR using supported computer-use actions.
- Attach `video.mp4` to a GitHub issue or PR description; H.264 MP4 is a [supported attachment format](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files), subject to upload limits.
- Render an already saved capture in GitHub Actions with Python and FFmpeg. Fresh capture needs the local computer-use runtime and desktop; this repository does not provide a hosted capture runner.

Git commands, `gh`, GitHub MCP/API calls, code edits, and GitHub Copilot actions are outside the capture path. Showandtell does not upload recordings automatically.

## Limits

- **Snapshots, not live footage.** Page animation, scroll transitions, and per-character typing between observations are not preserved. Cursor movement is reconstructed, not the original ghost cursor's exact trajectory.
- Coordinate clicks/drags can animate when a preceding screenshot exists. Accessibility-index actions supply no public pointer coordinates, so no position is invented.
- The screenshot `cua.getApp(...)` itself takes is not captured; the handle does not exist yet. The first frame comes from the first observation or, in `actions` mode, the first action.
- Use public unified `cua` app/tab methods with named handles. Frozen handles cannot be instrumented and produce an `immutable-target` warning. Direct Playwright and older browser-only tools are not instrumented.
- Native screenshots may contain the engine's ghost cursor, so native videos can show duplicate cursors. Browser screenshots tested for the original demo were clean.
- Capture needs an engine that lets REPL code write local files. Codex desktop does; a bare launch of the engine (for example by Claude) does not, and the recorder then reports a storage warning while the UI action remains usable.

## Local tools

From a clone:

```sh
sh plugins/showandtell/scripts/run.sh doctor
sh plugins/showandtell/scripts/run.sh status
sh plugins/showandtell/scripts/run.sh status /path/to/capture
sh plugins/showandtell/scripts/run.sh export /path/to/capture
sh plugins/showandtell/scripts/run.sh render /path/to/capture
sh plugins/showandtell/scripts/run.sh import /path/to/rollout.jsonl -o /path/to/capture
```

`export` records status and errors; `render` is the direct renderer. `session.json` is the portable screenshot/action manifest. `export.json` stores current export status and warnings. `SHOWANDTELL_HOME` changes capture storage. Claude's installed launcher is `sh ~/.showandtell/runtime/scripts/run.sh`.

The legacy importer reads saved Codex CUA/browser MCP results without executing their code. It cannot recover missing frames or exact pointer paths.

Marker logs omit typed text, key values, URLs, app names, and raw tool code. **Screenshots contain whatever is visible.** Review videos before sharing. [Data handling](PRIVACY.md) · [Support](https://github.com/milind-soni/showandtell/issues)

## Packaging and development

The plugin has a portable `plugin.json` plus the Codex compatibility manifest. OpenAI directory publication remains separate; see [SUBMISSION.md](SUBMISSION.md). Build the archive with:

```sh
python3 scripts/package.py
```

This creates `dist/showandtell-0.5.0.zip` and its SHA-256 checksum. The archive includes only plugin files, excluding captures and development material. Claude setup discovers the runtime already installed on your Mac; that runtime is not redistributed.

No Python or Node packages are required. Node is needed only for recorder checks:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/test_render.py
node --test tests/test_capture.mjs
```

The recorder tests model the engine as REPL code sees it: a read-only `cua.computer` proxy, a frozen `nodeRepl`, observations that return a short-lived screenshot file, and AX text that diffs against the previous observation. They assert that the recorder never writes to those engine objects. Hook checks cover first-call preservation, pre-hook collection, retried calls, Claude prompt/session boundaries, detached export, concurrent status reads, and that the hook process loads no heavy modules. Renderer checks produce a real MP4 and verify it with FFprobe.

For a local Codex installation: `codex plugin marketplace add /absolute/path/to/showandtell`, then `codex plugin add showandtell@showandtell`.

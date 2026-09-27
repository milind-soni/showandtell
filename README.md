# showandtell

Turn Codex computer use into a video. Reuse its screenshot observations, add a smooth animated cursor, and render a local MP4 in the background. No screen-recording process, web service, account, or editor.

[Install](#install) · [Performance](#performance) · [GitHub usage](#using-it-with-github) · [Download v0.3.0 preview](https://github.com/milind-soni/showandtell/releases/tag/v0.3.0)

[Watch the real browser demo](demo/showandtell.mp4)

![Showandtell video preview](demo/preview.png)

## Install

Requires a current Codex with command hooks and unified computer use, **Python 3.10+**, and **FFmpeg**. Tested on macOS with Codex CLI 0.153.4. Linux export is supported; Windows capture is not supported in this release.

**1. Install.** On macOS, paste this into Terminal:

```sh
curl -fsSL https://raw.githubusercontent.com/milind-soni/showandtell/main/install.sh | sh
```

The installer checks Codex CLI, Python, and FFmpeg, uses your existing [Homebrew](https://brew.sh) to install anything missing, then installs the plugin from this GitHub repository. If everything is already present, Homebrew is unnecessary. You can [inspect the installer](install.sh) first. It does not install Homebrew or grant hook trust.

**2. Enable capture.** Review and trust Showandtell's hooks in Codex (`/hooks` in the CLI). Installing the plugin does **not** grant hook trust. See [OpenAI's hook setup](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks).

**3. Use it.** Start a new Codex desktop chat and ask:

> Use Showandtell to make a video of this walkthrough.

Once enabled, hooks log supported computer-use actions and save existing screenshot observations in every chat where the plugin is active. Videos render in the background after each turn and appear in `~/.showandtell/<session>/<turn>/video.mp4`. Disable the plugin or its hooks to stop capturing. No recording is uploaded.

### Try it in a new chat

Paste this into a new Codex desktop chat:

> Use Showandtell to record a short walkthrough of https://github.com/milind-soni/showandtell. Browse the README, open Releases, and go back. Use coordinate clicks for smooth cursor animation. Verify that screenshots were saved, then give me the MP4.

This requires no local demo server or GitHub sign-in. Let the turn finish so the background export hook can run. Its result may arrive on your next message; ask **“Show me the latest Showandtell video from this chat.”** A text-only accessibility workflow produces no screenshot frames and cannot become a video. Check that frames were saved before claiming a recording.

### Manual installation

```sh
brew install --cask codex # only if Codex CLI is missing
brew install python ffmpeg # only if missing
codex plugin marketplace add milind-soni/showandtell
codex plugin add showandtell@showandtell
```

Then follow steps 2 and 3 above. No npm package, API key, or separate MCP server is needed.

### Update or uninstall

Finish active recordings before updating. Rerun the installer, or update a GitHub-backed installation manually:

```sh
codex plugin marketplace upgrade showandtell
codex plugin add showandtell@showandtell
```

Review any changed hooks and start a **new chat** after an update. Existing chats can retain old hooks or recorder wrappers; restart Codex if an old-version cache path still appears.

To uninstall:

```sh
codex plugin remove showandtell@showandtell
```

Saved videos stay in `~/.showandtell/` until you delete them.

### Troubleshooting

| Problem | What to do |
| --- | --- |
| Missing Homebrew | Install the missing prerequisites using [Homebrew](https://brew.sh), then rerun the installer. |
| Codex does not recognize `plugin` | Update Codex CLI; this release was checked with 0.153.4. |
| A local marketplace already uses the name `showandtell` | Keep the local installation and reinstall with `codex plugin add showandtell@showandtell` after updating its source. The public installer deliberately does not replace a local marketplace. |
| No video | Check hook trust, use a new desktop chat, and confirm actions use unified computer use. Ordinary chat, shell commands, and API calls do not produce video frames. |
| Hook points to a missing old version after updating | Start a new chat or restart Codex to reload the installed hooks. |
| Capture reports a storage error | The computer-use runtime must permit local file writes; report the failure rather than treating the recording as complete. |

## What happens

1. `PreToolUse` adds a small recorder to `cua_repl.js` after its required discovery call.
2. The recorder logs public app/tab actions and copies the screenshot bytes returned by existing `getScreenshot` and `getAXStateAndScreenshot` observations into private local files. Default reuse mode makes **zero additional screenshot requests**.
3. `PostToolUse` collects those files. A native asynchronous `Stop` hook recovers remaining files and renders 1280×800 H.264 at 60 fps with eased cursor travel, click ripples, drag motion, and shortened idle pauses while Codex can continue.

Export is headless. Capture uses Codex's existing app/browser access; native applications still need a running desktop. The live demo used a hidden Codex browser tab, six screenshots, and three clicks. No continuous display recording was used.

**Hook permission behavior:** Codex currently requires `permissionDecision: "allow"` with `updatedInput` to rewrite a tool call. Showandtell uses this only for the exact CUA JavaScript tool name. Review this behavior before trusting the hook; it is not a passive observer. It does not install a PermissionRequest hook or edit trust settings. See [Codex hooks](https://learn.chatgpt.com/docs/hooks) and [plugin packaging](https://developers.openai.com/plugins/build/plugins).

## Performance

**Lightweight is the default in 0.3.0.** It reuses normal screenshot observations and performs no extra screen captures. Action logging, small local writes, and pre/post hook processes still take time. Writes are awaited to avoid losing frames; it is not zero-overhead or entirely asynchronous capture. Export uses Codex's [background hooks](https://learn.chatgpt.com/docs/hooks#run-hooks-in-the-background), so the turn does not wait for FFmpeg. No daemon or separate server is needed.

The tradeoff is image coverage: accessibility text is not an image, initial discovery screenshots may be inaccessible, and several actions may happen between screenshot observations. The video holds the last observed image until a new one arrives. Actions without a preceding screenshot of their surface have no synthetic cursor; a turn without any frames produces a clear warning and no video.

For the old before/after behavior, set `SHOWANDTELL_CAPTURE=full` in the environment launching Codex. Full mode adds two screenshots per supported action. Start a fresh chat after changing modes. Background rendering remains enabled in either mode.

Baseline measurements of **0.2.0's full capture path** on September 27, 2026, using an Apple M5 with 24 GiB RAM, macOS 26.3.1, and Codex CLI 0.153.4:

| Measurement | Result | Scope |
| --- | --- | --- |
| Native Blender screenshot | 416 ms median; 379–471 ms range | Six sequential `getScreenshot({emit:false})` calls; about 0.78 MB each. No UI action or file write included. |
| Two extra screenshots per action | About 0.83 seconds | Estimate from the screenshot sample, before hook and storage costs. |
| Pre/post hook processes | About 65 ms each | Nine runs of each through the launcher; PostToolUse had no images to collect. About 130 ms per CUA call, excluding the Codex dispatcher. |
| Render a saved 13.35-second Blender video | 1.72 seconds median; 1.56–2.15 seconds range | Three full exports of 12 saved screenshots to 1280×800, 60 fps H.264. Export timing only. |

Default reuse mode removes those two extra screenshot calls per action; the hook and file-work costs remain. Rendering still consumes CPU and disk in the background. These component measurements are not an end-to-end benchmark of 0.3.0 or a speed guarantee. Browser capture, app load, resolution, disk speed, and longer recordings can change the result.

Background results are delivered at Codex's next safe point, which can be your next message. Closing the session can cancel an unfinished render; keep the saved capture and rerun the local render command if needed. An existing `video.mp4` is replaced only after a successful export.

Normal capture keeps its extra screenshot bytes out of the model conversation and makes no extra LLM API requests itself. Skill instructions, hook messages, and rewritten tool input can still affect context and token usage; this is not a zero-token-overhead claim. Capture files consume disk space until deleted. Disable the plugin or hooks when you do not need videos.

## Using it with GitHub

| Use case | Support |
| --- | --- |
| Install and update from this repository | Yes; no directory approval is needed for the GitHub installation route. |
| Record a GitHub browser walkthrough or demo a local app for a PR | Yes, when Codex uses supported unified `cua` actions. |
| Attach the resulting video to a PR or issue | Yes. Drag `video.mp4` into the GitHub description or comment editor. H.264 MP4 is a [supported attachment format](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files). Upload limits apply. |
| Record `git`, `gh`, GitHub MCP/API calls, or ordinary code edits | No; these do not pass through the computer-use capture hook. |
| Use GitHub Actions | A saved capture can be rendered with Python and FFmpeg. Automatic fresh capture requires Codex's computer-use runtime and trusted hooks; this release does not provide a GitHub Actions capture integration. |
| Use GitHub Copilot as the recorder | Not supported; the hooks target Codex's unified computer-use tool. |

For a PR demo, ask: **“Use Showandtell to demonstrate the changes in my local app, then give me the MP4 for the PR.”** Showandtell saves the video locally; sharing it is a separate action. A README can link to a committed demo video as this repository does.

## Current limits

- **Coordinate clicks and drags:** animated cursor when a preceding screenshot of that surface is available. Accessibility-index actions have no invented cursor position; the public API does not reveal their resolved targets.
- **Snapshots, not live footage:** page animation, scroll transitions, and per-character typing between snapshots are not preserved. Cursor movement is reconstructed, not the original ghost cursor's exact trajectory.
- Use unified `cua` app/tab methods and mutable `let`/`var` handles. First discovery remains untouched. Initial `const` handles on immutable targets can miss capture; the bundled skill explains recovery. Older browser-only tools and direct Playwright calls are not instrumented.
- Native screenshots may already contain Codex's ghost cursor. Showandtell cannot reliably remove it, so native videos can show duplicate cursors. The tested browser screenshots are clean.
- Reuse mode only sees bytes returned by the supported public screenshot methods; it cannot recover arbitrary internal screenshots or turn accessibility text into images. Full mode adds capture time. The recorder adds no duplicate image output. Long turns take longer to render; interrupted exports can be rerun.
- Legacy transcript import cannot reconstruct truncated image data. Normal capture no longer depends on transcript images. Keep unrelated image emissions out of legacy capture calls to avoid ambiguous pairing.
- Hook handlers and a real capture/export were tested separately. The normal user-trusted hook dispatcher must be enabled in your installation; this project does not silently grant that trust.
- Native capture requires permission to write local files from the computer-use runtime. If that runtime blocks file access, capture reports a storage warning; it does not weaken permissions or silently fall back to a truncated recording.

## Local tools

From a clone:

```sh
sh plugins/showandtell/scripts/run.sh doctor
sh plugins/showandtell/scripts/run.sh render /path/to/capture
sh plugins/showandtell/scripts/run.sh import /path/to/rollout.jsonl -o /path/to/capture
```

The importer reads saved CUA/browser MCP results without executing their code. It cannot recover omitted frames or pointer paths. `session.json` is the portable screenshot/action manifest; `export.json` contains warnings. `SHOWANDTELL_HOME` changes the storage directory; `SHOWANDTELL_DISABLED=1` makes hooks do nothing (set in the environment launching Codex).

Marker logs omit typed text, keys, URLs, and raw tool code. **Screenshots still contain whatever is visible.** Captures remain on disk until you remove them. Review videos before sharing.

[Data handling](PRIVACY.md) · [Support](https://github.com/milind-soni/showandtell/issues)

## Plugin directory submission

GitHub installation is available without directory approval. The plugin directory upload and review materials are described in [SUBMISSION.md](SUBMISSION.md). Build the upload archive with:

```sh
python3 scripts/package.py
```

This creates `dist/showandtell-0.3.0.zip` and a SHA-256 checksum. It includes only the plugin, not local captures, account screenshots, or development test files. Upload through OpenAI's **Skills only** submission route when available to your account; a remote MCP server is not part of this plugin.

## Development

No Python packages or Node packages are required. Node is only needed for the capture-helper checks.

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/test_render.py
node --test tests/test_capture.mjs
python3 -m http.server 8768 --bind 127.0.0.1 --directory demo
```

Open `http://127.0.0.1:8768` through Codex computer use for the disposable live fixture. Click Calm, Bold, and Create walkthrough. The renderer check generates a real MP4, inspects it with FFprobe, and checks chronology, cursor endpoints, frame bounds, and atomic failure recovery.

Release 0.2.0 passed 24 Python hook/installer checks, 13 JavaScript capture checks, and the real MP4 renderer check. A live Blender test saved 3024×1780 screenshots directly to disk and exported a playable 60 fps video with the tool-result content deliberately discarded. The extracted release ZIP also passed runtime diagnostics. These checks do not replace testing the trusted hook dispatcher in a fresh Codex chat.

Release 0.3.0 passes 25 Python hook/installer checks, 17 JavaScript checks, and the real MP4 renderer check. Coverage includes zero extra screenshot requests in reuse mode, unchanged observation results, concurrent observations, optional full capture, large raw images, and text-only turns. Background dispatch uses Codex's documented `async` hook support; its fresh-chat dispatcher has not been validated end to end here.

For local installation, use `codex plugin marketplace add /absolute/path/to/showandtell`, then the same plugin-add command above. Packaging lives in `.agents/plugins/marketplace.json` and `plugins/showandtell/`.

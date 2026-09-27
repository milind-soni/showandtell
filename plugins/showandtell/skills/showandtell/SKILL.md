---
name: showandtell
description: Turn Codex computer-use and browser-use actions into a local MP4 with smooth cursor motion. Use when the user asks to record a walkthrough, make a demo video, or export a Showandtell capture.
---

# Showandtell

The plugin's hooks log supported `cua_repl.js` actions, reuse normal screenshot observations, and render in the background after the turn ends. Default reuse mode never requests extra screenshots. Follow the computer-use tool's first-call and observation rules. Do not manually add the capture bootstrap if hooks are working. Start a new chat after upgrading so older recorder wrappers are not retained.

- Use the unified `cua` API for both apps and browser tabs. Keep a named `let` or `var` handle returned by `cua.getApp`, `cua.getTab`, or `cua.createBrowserTab`. The required first discovery call stays untouched. The next action call installs recording and wraps that handle. An initial immutable `const` handle may not be instrumentable; reacquire it into a new mutable binding if capture reports this.
- Reuse mode copies raw bytes returned by `getScreenshot` and the optional `screenshot` in `getAXStateAndScreenshot`, preserving their normal behavior and output. It does not add duplicate image emissions. A `getAXState` string is not a screenshot; internal or initial discovery images may be inaccessible. Do not claim every action has a before/after frame. If no screenshots were observed, explain that no video can be rendered. Do not add redundant screenshots solely to work around this mode without explaining the added cost.
- Direct local files survive transcript truncation. If importing older transcript recordings, keep unrelated image emissions separate because text/image pairing may be ambiguous.
- Coordinate actions record cursor targets. Accessibility-index action coordinates are not exposed by the public API, so the video hides its synthetic pointer for those actions. A coordinate action also needs a preceding screenshot of that surface. Explain these limits instead of claiming exact ghost-cursor replay. When the user explicitly asks for a cursor demonstration, use fresh screenshots and coordinate actions for that demonstration.
- An action snapshot is not a live recording. Animation, loading, scrolling, and typing between snapshots are not preserved. The renderer supplies smooth cursor motion, holds, and click ripples.
- Stop is a native asynchronous Codex hook. Rendering starts after the turn; it may finish after the answer. Its result may arrive on the next user turn. Check `video.mp4` and `export.json` before claiming completion; do not wait on every turn or start duplicate exports. Closing Codex can cancel background hooks; the saved capture can be rendered again. Captures live in `~/.showandtell/<session>/<turn>/`; `session.json` lists frames/actions and `export.json` reports export warnings. Never upload recordings without the user's request.
- Optional full capture (`SHOWANDTELL_CAPTURE=full` in the environment launching Codex) adds screenshots before/after every supported action, as in version 0.2.0. It costs extra capture latency. Do not silently switch to full mode or change the user's environment.
- If export fails, run `sh <plugin-root>/scripts/run.sh doctor`, fix the reported dependency, and use `sh <plugin-root>/scripts/run.sh render <capture-directory>` to retry. Resolve `<plugin-root>` from this skill's directory (two levels up). The launcher finds Homebrew runtimes even when desktop Codex has a different PATH.
- If capture reports `capture-storage-unavailable` or `capture-storage-write-failed`, report the error and inspect local file access. Do not bypass sandbox permissions, claim a complete video, or rely on truncated transcript images as a replacement.
- If hooks have not been trusted, tell the user to review Showandtell in Codex's `/hooks` screen. Do not alter hook trust or approval settings. Do not claim automatic capture works before confirming recorded frames.

Exports are local. Screenshots can contain visible private information. The marker log stores action kinds, times, surfaces, and coordinates, but omits typed text and raw tool code.

---
name: showandtell
description: Turn Codex computer-use and browser-use actions into a local MP4 with smooth cursor motion. Use when the user asks to record a walkthrough, make a demo video, or export a Showandtell capture.
---

# Showandtell

The plugin's hooks save screenshots directly to local files before/after supported `cua_repl.js` actions and render a video when the turn ends. Follow the computer-use tool's first-call and observation rules. Do not manually add the capture bootstrap if hooks are working. Start a new chat after upgrading so older recorder wrappers are not retained.

- Use the unified `cua` API for both apps and browser tabs. Keep a named `let` or `var` handle returned by `cua.getApp`, `cua.getTab`, or `cua.createBrowserTab`. The required first discovery call stays untouched. The next action call installs recording and wraps that handle. An initial immutable `const` handle may not be instrumentable; reacquire it into a new mutable binding if capture reports this.
- Normal capture does not need screenshots emitted in tool output. Direct local files survive transcript truncation. If importing older transcript recordings, keep unrelated image emissions separate because text/image pairing may be ambiguous.
- Coordinate actions record cursor targets. Accessibility-index actions still capture state changes, but their coordinates are not exposed by the public API, so the video hides its synthetic pointer for those actions. Explain this limitation instead of claiming exact ghost-cursor replay. When the user explicitly asks for a cursor demonstration, use fresh screenshots and coordinate actions for that demonstration.
- An action snapshot is not a live recording. Animation, loading, scrolling, and typing between snapshots are not preserved. The renderer supplies smooth cursor motion, holds, and click ripples.
- Report the output path returned by the Stop hook. Captures live in `~/.showandtell/<session>/<turn>/`; `session.json` lists frames/actions and `export.json` reports export warnings. Never upload recordings without the user's request.
- If export fails, run `sh <plugin-root>/scripts/run.sh doctor`, fix the reported dependency, and use `sh <plugin-root>/scripts/run.sh render <capture-directory>` to retry. Resolve `<plugin-root>` from this skill's directory (two levels up). The launcher finds Homebrew runtimes even when desktop Codex has a different PATH.
- If capture reports `capture-storage-unavailable` or `capture-storage-write-failed`, report the error and inspect local file access. Do not bypass sandbox permissions, claim a complete video, or rely on truncated transcript images as a replacement.
- If hooks have not been trusted, tell the user to review Showandtell in Codex's `/hooks` screen. Do not alter hook trust or approval settings. Do not claim automatic capture works before confirming recorded frames.

Exports are local. Screenshots can contain visible private information. The marker log stores action kinds, times, surfaces, and coordinates, but omits typed text and raw tool code.

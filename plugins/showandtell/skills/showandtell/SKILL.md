---
name: showandtell
description: Turn supported Codex or Claude computer-use actions into a local MP4 with smooth cursor motion. Use when asked to record a walkthrough, make a demo video, or export a Showandtell capture.
---

# Showandtell

Enabled hooks record supported unified computer-use calls and queue a local video after the turn. Follow the computer-use tool's first-call and observation rules; do not bootstrap capture by hand when hooks work. Start a new chat after upgrading.

- Mac apps: the engine already takes a screenshot for every observation (`getAXState`, `getScreenshot`, `getAXStateAndScreenshot`, `cua.getApp`), and Showandtell saves that image, so text-only observations are video frames at no extra cost. Default `actions` mode also saves the screen after each action (one extra engine observation per action), so batched actions keep every state. After that private capture your next `getAXState` on the app returns a full tree instead of a diff; that is expected.
- Browser tabs: frames come from `getScreenshot`/`getAXStateAndScreenshot` results and, in `actions` mode, from a screenshot after each action. `getAXState` on a tab has no image.
- Coordinate actions animate the cursor when a frame of that surface precedes them; accessibility-index actions expose no coordinates, so their pointer is hidden. For a cursor demonstration, use coordinate actions after a screenshot. Motion is reconstructed; typing, scrolling, and animations between frames are not live footage.
- Keep handles from `cua.getApp`, `cua.getTab`, or `cua.createBrowserTab` in named `let`/`var`/`const` bindings. Mac app handles need nothing else. Tab handles are instrumented in place; an `immutable-target` warning means that tab cannot be recorded.
- Stop collects the remaining files and launches a short detached export; the answer does not wait for rendering. Check `status`, `video.mp4`, and `export.json` before claiming completion; do not start duplicate exports. Captures live under `~/.showandtell/<session>/<turn>/` or `claude-<session>/<turn>/`; a failed or interrupted export can be retried from the saved capture. Never upload without the user's request.
- Local launcher: `sh <plugin-root>/scripts/run.sh status [capture-directory]`, `doctor`, or `export <capture-directory>`. In a Codex package, `<plugin-root>` is two levels above this skill's directory. For the installed Claude skill at `~/.claude/skills/showandtell`, use `~/.showandtell/runtime`. `SHOWANDTELL_HOME` overrides capture storage.
- Claude support targets exactly `mcp__codex-cu__js` with normal Claude permissions and the bundled local Mac MCP; the backend needs a running desktop and app consent. Report consent or missing-metadata blockers without auto-approving or forging host metadata.
- `SHOWANDTELL_CAPTURE=reuse` (nothing extra requested) or `full` (before and after every action) in the environment launching the agent changes the mode; do not silently change modes. `SHOWANDTELL_DISABLED=1` disables hooks. To stop persistent capture, disable the plugin/hooks or remove Showandtell's Claude hook entries.
- Storage warnings (`capture-storage-unavailable`, `capture-storage-write-failed`) mean capture is incomplete; report them rather than weakening permissions. If Codex hooks are not trusted, direct the user to `/hooks`; do not change trust settings. Check saved frames before claiming automatic recording worked.

Exports stay local. Marker metadata omits typed text, keys, URLs, app names, and raw tool code; screenshots may contain visible private information.

# Showandtell submission materials

Package type: **Skills only**, with Codex command hooks and local scripts. No remote MCP server, authentication service, or hosted recording service is required. Optional Claude setup references the existing locally installed bundled computer-use MCP; that runtime is not redistributed in the ZIP.

Public distribution: [GitHub installation](README.md#install). OpenAI directory publication is separate and has not been completed. See the [official submission guide](https://developers.openai.com/plugins/deploy/submission).

## Listing

- Name: Showandtell
- Publisher: Milind Soni
- Category: Productivity
- Short description: Computer use becomes a video.
- Description: Turn supported Codex computer-use actions into local MP4 walkthroughs with smooth cursor motion. Captures a screenshot after each action, saves normal screenshot observations, and renders with FFmpeg in the background. Capture adds awaited screenshot and file-write costs. Requires local desktop computer use, Python 3.10+, FFmpeg, and enabled hooks. The experimental Claude adapter depends on native app consent; browser operation on the tested external-client backend is unsupported.
- Website: https://github.com/milind-soni/showandtell
- Support: https://github.com/milind-soni/showandtell/issues
- Data handling: https://github.com/milind-soni/showandtell/blob/main/PRIVACY.md
- Logo: `plugins/showandtell/assets/logo.png`
- Starter prompt: Use Showandtell to make a video of this walkthrough.
- Starter prompt: Use Showandtell to export my saved capture as an MP4.

## Review setup

Use macOS with current Codex desktop computer use. Run the installer, start a new chat, and review/enable the plugin in `/hooks`. Capture saves local files and therefore requires the computer-use runtime to permit those writes. Native apps need a running desktop; export itself is headless. This does not run in ordinary ChatGPT web chats without the Codex hook runtime.

For the browser fixture, clone the repository and run `python3 -m http.server 8768 --bind 127.0.0.1 --directory demo`. Use unified CUA methods with mutable `let` or `var` app/tab bindings and normal screenshot observations. No sign-in or review credentials are required. Inspect the resulting `session.json`, `export.json`, and `video.mp4` under `~/.showandtell/`. Default `actions` mode awaits a screenshot after each supported action and a baseline before the first action on a surface if that turn has no image of it. Normal observations are copied too. Only export is detached: Stop starts a short-lived job that can finish after the host exits, and `status` reports its state without waiting for encoding.

## Positive test cases

1. **Browser walkthrough.** Prompt: “Use Showandtell to open http://127.0.0.1:8768 in the Codex browser, choose Bold, and create a walkthrough.” Expect a screenshot after each supported action, a baseline when needed, normal observations, action metadata, and a playable local MP4 when background export completes. A hidden browser tab may be used; the capture calls still add latency.
2. **Smooth cursor.** Prompt: “Use Showandtell to demonstrate the Calm and Bold buttons with coordinate clicks.” Expect coordinates within the source screenshot, smoothly animated travel, and click feedback on successful actions. Do not claim these are exact native ghost-cursor samples.
3. **Native app.** Prompt: “Use Showandtell to show the front and right views of this disposable Blender scene.” Expect saved native screenshots and a local video. Keyboard actions have no invented pointer coordinates. The native ghost cursor may remain visible in snapshots.
4. **Saved capture export.** Prompt: “Use Showandtell to export this saved capture directory as an MP4.” Provide a capture from test 1. Expect a playable 1280×800, 60 fps H.264 video without operating an app or accessing a recording server.
5. **Interrupted collection.** In the local test harness, save screenshot sidecars and omit the PostToolUse result. Run Stop. Expect the pending files to be collected and rendered. Repeating Stop with an unchanged saved session must not duplicate actions or unnecessarily rerender.

## Negative test cases

1. **Hooks not trusted.** Prompt: “Make the video without enabling the plugin hooks.” Expect an explanation that automatic capture needs user-reviewed hook trust. Do not change trust settings or claim that unrecorded actions were captured.
2. **Unsafe or incomplete saved capture.** Provide a disposable session whose screenshot path escapes the capture directory, or a transcript with missing image bytes. Expect path rejection or an explicit incomplete-capture warning. Do not read unrelated files or fabricate missing frames.
3. **Unavailable capture storage.** Test with local writes blocked in a disposable runtime. Expect a storage warning while the requested UI action remains usable. Do not weaken permissions, upload data, or claim a complete recording.
4. **Reuse without images.** Set `SHOWANDTELL_CAPTURE=reuse`, start a new chat, and perform actions followed only by `getAXState`. Expect saved action metadata and an explicit no-frames warning, with no fabricated video or extra screenshot requests. Default `actions` mode instead requests a screenshot after each action.

## Release notes: 0.4.0

Default capture now saves the resulting screen after every supported action, including actions in the same tool call, with an initial baseline per surface/turn when needed. Normal screenshot observations are still copied. Zero-extra-screenshot reuse and before/after full capture are optional modes. These are awaited snapshots, not live footage or asynchronous capture.

Added optional Claude Code setup and hook adaptation for the installed bundled Mac MCP, with preserved tool permissions, private configuration, stable runtime copies, separate prompt turns, and failed-call/session-end recovery. Native app approval blocked the headless Claude test, and the external browser test required unavailable Codex turn metadata. Export uses a detached one-off process to survive host exit, with per-turn locking and persisted status/errors. Repeated pre-hooks can append safely to an existing call's capture. Portable plugin metadata is included alongside the Codex compatibility manifest. Review changed hooks and start a new chat after upgrading.

## Remaining publisher steps

Complete individual or business identity verification in the publishing OpenAI organization. The submission account needs Apps Management write access and the Skills only creation option. On the checked account, the portal showed only With MCP; do not submit a dummy remote server to work around that limitation.

Once available, upload the generated ZIP, copy the listing and test cases above, select the verified publisher and intended availability, review the actual policy attestations, and submit for review. Approval does not publish automatically; publication is a separate portal action. This document does not make policy attestations or accept agreements on the publisher's behalf.

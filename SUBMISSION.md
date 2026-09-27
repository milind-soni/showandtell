# Showandtell submission materials

Package type: **Skills only**, with Codex command hooks and local scripts. No MCP server, authentication service, or hosted recording service is required.

Public distribution: [GitHub installation](README.md#install). OpenAI directory publication is separate and has not been completed. See the [official submission guide](https://developers.openai.com/plugins/deploy/submission).

## Listing

- Name: Showandtell
- Publisher: Milind Soni
- Category: Productivity
- Short description: Computer use becomes a video.
- Description: Turn supported Codex computer-use actions into local MP4 walkthroughs with smooth cursor motion. Reuses normal screenshot observations and renders in the background with FFmpeg. Requires desktop computer use, Python 3.10+, FFmpeg, and trusted command hooks. Text-only observations cannot produce a video.
- Website: https://github.com/milind-soni/showandtell
- Support: https://github.com/milind-soni/showandtell/issues
- Data handling: https://github.com/milind-soni/showandtell/blob/main/PRIVACY.md
- Logo: `plugins/showandtell/assets/logo.png`
- Starter prompt: Use Showandtell to make a video of this walkthrough.
- Starter prompt: Use Showandtell to export my saved capture as an MP4.

## Review setup

Use macOS with current Codex desktop computer use. Run the installer, start a new chat, and review/enable the plugin in `/hooks`. Capture saves local files and therefore requires the computer-use runtime to permit those writes. Native apps need a running desktop; export itself is headless. This does not run in ordinary ChatGPT web chats without the Codex hook runtime.

For the browser fixture, clone the repository and run `python3 -m http.server 8768 --bind 127.0.0.1 --directory demo`. Use unified CUA methods with mutable `let` or `var` app/tab bindings and normal screenshot observations. No sign-in or review credentials are required. Inspect the resulting `session.json`, `export.json`, and `video.mp4` under `~/.showandtell/`. Default reuse mode makes no extra screenshot requests. Stop renders through Codex's native background-hook support; results may be delivered on the next user turn. Closing the session can cancel a pending render.

## Positive test cases

1. **Browser walkthrough.** Prompt: “Use Showandtell to open http://127.0.0.1:8768 in the Codex browser, choose Bold, and create a walkthrough.” With normal screenshot observations, expect those saved images, action metadata, and a playable local MP4 when the background export completes. Do not expect a new screenshot for every action. A hidden browser tab may be used.
2. **Smooth cursor.** Prompt: “Use Showandtell to demonstrate the Calm and Bold buttons with coordinate clicks.” Expect coordinates within the source screenshot, smoothly animated travel, and click feedback on successful actions. Do not claim these are exact native ghost-cursor samples.
3. **Native app.** Prompt: “Use Showandtell to show the front and right views of this disposable Blender scene.” Expect saved native screenshots and a local video. Keyboard actions have no invented pointer coordinates. The native ghost cursor may remain visible in snapshots.
4. **Saved capture export.** Prompt: “Use Showandtell to export this saved capture directory as an MP4.” Provide a capture from test 1. Expect a playable 1280×800, 60 fps H.264 video without operating an app or accessing a recording server.
5. **Interrupted collection.** In the local test harness, save screenshot sidecars and omit the PostToolUse result. Run Stop. Expect the pending files to be collected and rendered. Repeating Stop with an unchanged saved session must not duplicate actions or unnecessarily rerender.

## Negative test cases

1. **Hooks not trusted.** Prompt: “Make the video without enabling the plugin hooks.” Expect an explanation that automatic capture needs user-reviewed hook trust. Do not change trust settings or claim that unrecorded actions were captured.
2. **Unsafe or incomplete saved capture.** Provide a disposable session whose screenshot path escapes the capture directory, or a transcript with missing image bytes. Expect path rejection or an explicit incomplete-capture warning. Do not read unrelated files or fabricate missing frames.
3. **Unavailable capture storage.** Test with local writes blocked in a disposable runtime. Expect a storage warning while the requested UI action remains usable. Do not weaken permissions, upload data, or claim a complete recording.
4. **Text-only observations.** Perform actions followed only by `getAXState`. Expect saved action metadata and an explicit no-frames warning, with no fabricated video or extra screenshot requests.

## Release notes: 0.3.0

Default capture now reuses normal screenshot observations without requesting extra screenshots. Optional full mode preserves the old before/after behavior. Export uses native asynchronous Stop hooks, with no custom daemon. Raw screenshot bytes remain local and independent of truncated transcripts. Text-only turns report that no video can be rendered. The updated hook definition needs review, and a new chat is required after upgrading.

## Remaining publisher steps

Complete individual or business identity verification in the publishing OpenAI organization. The submission account needs Apps Management write access and the Skills only creation option. On the checked account, the portal showed only With MCP; do not submit a dummy remote server to work around that limitation.

Once available, upload the generated ZIP, copy the listing and test cases above, select the verified publisher and intended availability, review the actual policy attestations, and submit for review. Approval does not publish automatically; publication is a separate portal action. This document does not make policy attestations or accept agreements on the publisher's behalf.

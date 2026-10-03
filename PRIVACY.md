# Showandtell data handling

Showandtell is a local recorder for supported Codex and Claude computer use, maintained by Milind Soni. It does not operate a recording server, require a Showandtell account, or send recordings to the maintainer.

When its command hooks are enabled, it saves screenshots, action times, surface identifiers, action kinds, available pointer coordinates, and success/failure status. Default `actions` mode requests a screenshot after each supported action and a baseline before a surface's first action when the current turn has no image of that surface. It also copies normal screenshot observations. Optional `reuse` mode requests no extra screenshots; optional `full` mode requests screenshots before and after every supported action. Capture is active in chats where the plugin and its hooks are enabled. Screenshots can contain anything visible in the selected app or browser tab, including private information.

Showandtell's action metadata omits typed text, key values, URLs, and raw tool code. That does not remove information visible in screenshots. The agent client continues handling the conversation and normal tool results under its own settings and policies; Showandtell does not change that behavior. Using Claude to operate an app means normal tool observations are handled by Claude under its settings.

Captures and videos remain on the user's computer under `~/.showandtell/`, or the directory configured with `SHOWANDTELL_HOME`. Temporary capture files are collected into a saved session. A short-lived detached export process writes local export status and a private diagnostic log; it can finish after the chat process exits. Saved captures, videos, and logs remain until the user deletes them. Disable the plugin or its hooks to stop capture. `SHOWANDTELL_DISABLED=1` also disables hooks when set in the environment launching the agent.

The installer contacts GitHub to download the plugin and, if prerequisites are missing, uses an existing Homebrew installation to install Codex CLI, Python, or FFmpeg. Those downloads follow the respective services' policies. Showandtell has no analytics or telemetry endpoint.

Optional Claude setup copies the installed local computer-use MCP command, arguments, and environment into Claude's user MCP configuration. It also stores an owned copy under `~/.showandtell/runtime/` for safe updates, installs local hooks and a skill, and backs up an existing settings file before changing it. Configuration output mode instead writes private files at a user-selected path without changing user settings. These files describe the local runtime and should not be published. The bundled runtime is not uploaded or redistributed, and setup does not auto-approve tool access or change native app permissions.

Showandtell does not upload a video automatically. Review recordings before sharing them. If you explicitly ask Codex to share a recording using another tool, that destination's data handling applies.

For support, use [GitHub Issues](https://github.com/milind-soni/showandtell/issues). Do not attach private captures, credentials, or account information to a public issue.

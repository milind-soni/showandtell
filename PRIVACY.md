# Showandtell data handling

Showandtell is a local Codex plugin maintained by Milind Soni. It does not operate a recording server, require a Showandtell account, or send recordings to the maintainer.

When its command hooks are enabled, it saves normal screenshot observations from supported computer-use methods, action times, surface identifiers, action kinds, available pointer coordinates, and success/failure status. Default reuse mode does not request extra screenshots. Optional full mode captures extra screenshots before and after actions. Capture is active in chats where the plugin and its hooks are enabled. Screenshots can contain anything visible in the selected app or browser tab, including private information.

Showandtell's action metadata omits typed text, key values, URLs, and raw tool code. That does not remove information visible in screenshots. Codex itself continues handling the conversation and normal tool results under its own settings and policies; Showandtell does not change that behavior.

Captures and videos remain on the user's computer under `~/.showandtell/`, or the directory configured with `SHOWANDTELL_HOME`. Temporary capture files are collected into a saved session. Saved sessions and videos remain until the user deletes them. Disable the plugin or its hooks to stop capture. `SHOWANDTELL_DISABLED=1` also disables hooks when set in the environment launching Codex.

The installer contacts GitHub to download the plugin and, if prerequisites are missing, uses an existing Homebrew installation to install Codex CLI, Python, or FFmpeg. Those downloads follow the respective services' policies. Showandtell has no analytics or telemetry endpoint.

Showandtell does not upload a video automatically. Review recordings before sharing them. If you explicitly ask Codex to share a recording using another tool, that destination's data handling applies.

For support, use [GitHub Issues](https://github.com/milind-soni/showandtell/issues). Do not attach private captures, credentials, or account information to a public issue.

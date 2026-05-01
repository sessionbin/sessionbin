# sessionbin

A transcript pastebin for agentic sessions.

Upload a session file, get a shareable URL, and anyone with the link can view the server-rendered transcript.
Anonymous upload, delete-by-token.
No accounts, no dashboards.

Currently supported: Claude Code. Future transcript support for: OpenCode, Codex, Gemini CLI.

## How it works

1. Upload a raw session file (via web UI or API).
2. The server redacts secrets, parses the session, renders it to HTML, and stores it.
3. You get a share URL and a delete token.
4. Anyone with the URL sees the rendered transcript. Only you (with the token) can delete it.

A companion CLI lives at [sessionbin-cli](https://github.com/sessionbin/sessionbin-cli).

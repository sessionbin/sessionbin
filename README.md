# sessionbin

A transcript pastebin for agentic sessions.

Upload a session file, get a shareable URL, and anyone with the link can view the server-rendered transcript.
Anonymous upload, delete-by-token.
No accounts, no dashboards.

Currently supported: Claude Code and OpenCode. Future transcript support for: Codex, Pi, Gemini CLI.

## How it works

1. Upload a raw session file (via web UI or API).
2. The server redacts secrets, parses the session, renders it to HTML, and stores it.
3. You get a share URL and a delete token.
4. Anyone with the URL sees the rendered transcript. Only you (with the token) can delete it.

The companion CLI lives in [`cli/`](cli/) in this repo and is published to PyPI as
`sessionbin`.

## Local development

Everything needed to run and exercise the project lives in a container: the backend, the
CLI, `gitleaks`, and both supported agent harnesses so you can produce real sessions.

```bash
podman build -t sessionbin-dev -f dev/Containerfile dev/
podman run --rm -it -p 8000:8000 -v "$PWD":/repo:Z --name sessionbin-dev sessionbin-dev
```

The site is then at <http://127.0.0.1:8000>. The container syncs dependencies, installs
the CLI from `cli/`, applies migrations, and runs the dev server against your mounted
checkout, so edits reload live. The database and stored pastes go to `/state` inside the
container, never into your checkout.

To produce a real session and upload it, exec into the running container:

```bash
podman exec -it sessionbin-dev bash
cd /work && mkdir -p demo && cd demo          # any scratch directory
export ANTHROPIC_API_KEY=...                  # or pass --env-file to podman run

claude -p "..." --model claude-haiku-4-5      # Claude Code
opencode run -m anthropic/claude-haiku-4-5 "..."   # OpenCode

sessionbin upload --latest -y --server http://127.0.0.1:8000
```

Run the checks with `tox run` (inside the container or on the host).

**Adding support for a new harness?** Install it in `dev/Containerfile` as well, or the
dev container can no longer produce a real session to test the new adapter against.

Running the backend outside a container needs Python 3.14 and `gitleaks` on `PATH` — the
settings module raises at import without it.

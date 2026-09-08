# CLAUDE.md

## What this is

The CLI client for [sessionbin](https://sessionbin.dev), a transcript pastebin for
agentic coding sessions. `sessionbin upload` sends a session file to the server and
prints a share URL.

Published on PyPI as `sessionbin`. The backend lives in the repo root and is a separate
uv project that is not published.

**The distribution is `sessionbin` but the import package is `sessionbin_cli`.** They
differ because the backend also ships a `sessionbin` import package, and the two must not
collide. Keep the distribution name as-is — it is what users `pip install`, and the
console script is what they actually invoke.

## Invariants

- **The CLI never parses session files.** It uploads raw bytes; parsing happens
  server-side. The HTTP API is the only contract with the backend.
- **`~/.config/sessionbin/sessions.json` is the only record of delete tokens.** If it is
  lost, the user cannot delete their pastes. Writes are atomic and `0600`.
- **Server URL resolution has a fixed priority:** `--server` flag > `SESSIONBIN_URL` env
  var > config file > interactive prompt.
- **OpenCode uploads shell out to the `opencode` binary.** Sessions live in a SQLite DB,
  not as files, so `upload` runs `opencode export <id>` to get JSON. The binary must be
  on `PATH` (or at `~/.opencode/bin/opencode`), otherwise OpenCode uploads fail even
  though discovery succeeded.
- `detect.py`'s `DETECTORS` list is the extension point for new harnesses.

## Commands

Run these from the **repo root**, not from `cli/` — tox is configured there and knows to
install `./cli` for these envs.

```bash
tox run -e cli             # tests
tox run -e cli-typecheck   # mypy
tox run -e lint            # ruff, both packages
tox run -e check-format    # format check
```

To run the CLI itself: `uv run --project cli sessionbin --help`.

Inside the dev container the CLI is already installed as a uv tool, so just run
`sessionbin`. Do not `uv run` from `cli/` there — it re-syncs the shared environment and
breaks the running backend.

## Verification

Run `tox run` from the repo root after every code change and fix what fails.

## Conventions

- Python 3.10+, uv for everything. No `requirements.txt`.
- Fix lint errors at the source. No `# noqa`, no excluding files.
- **No underscore-prefixed "private" function names.** This is an application, not a
  published library, so there is no external API surface for the convention to protect.
- **Type annotations should describe what the code actually accepts.** If you reach for
  `typing.cast()` to bridge two things you control, the annotation is wrong — widen or
  correct it. A `cast` on genuinely untyped external data is fine.
- Tests live under `tests/`.

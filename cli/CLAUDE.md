# CLAUDE.md

## What this is

The CLI client for [sessionbin](https://sessionbin.dev), a transcript pastebin for
agentic coding sessions. `sessionbin upload` sends a session file to the server and
prints a share URL.

Published on PyPI as `sessionbin` — note the package name matches the *backend* repo's
name, not this one. The backend lives in a separate `sessionbin` repo and is not a PyPI
package.

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

## Running it locally

```bash
uv run --with . sessionbin --help
```

## Commands

```bash
tox -e py313          # tests
tox -e lint           # ruff lint
tox -e check-format   # ruff format check
tox -e typecheck      # mypy
```

`lint-fix` and `format` are the autofixing variants.

## Verification

Run all four checks after every code change and fix what fails. Do not skip any.

## Conventions

- Python 3.10+, uv for everything. No `requirements.txt`.
- Fix lint errors at the source. No `# noqa`, no excluding files.
- **No underscore-prefixed "private" function names.** This is an application, not a
  published library, so there is no external API surface for the convention to protect.
- **Type annotations should describe what the code actually accepts.** If you reach for
  `typing.cast()` to bridge two things you control, the annotation is wrong — widen or
  correct it. A `cast` on genuinely untyped external data is fine.
- Tests live under `tests/`.

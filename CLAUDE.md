# CLAUDE.md

## Introduction

sessionbin is the CLI client for [sessionbin](https://sessionbin.dev),
a transcript pastebin for agentic coding sessions.
Users run `sessionbin upload` to send a session file to the server and get a share URL back.
The CLI never parses session files, it uploads raw bytes over HTTP.
Its only contract with the backend is the HTTP API.

Published on PyPI as `sessionbin` (`pip install sessionbin`). The backend lives in a separate `sessionbin` repo and is not a PyPI package.

## Architecture

Five modules under `src/sessionbin/`:

- **`cli.py`**: Click command group with `upload`, `list`, and `delete` subcommands.

- **`api.py`**: `SessionbinClient` wrapping `httpx` for `POST /api/upload` and `DELETE /api/p/<slug>`.

- **`config.py`**: Server URL resolution: `--server` flag > `SESSIONBIN_URL` env var > `~/.config/sessionbin/config.toml` > interactive prompt.

- **`detect.py`**: Finds session files on disk. Currently discovers Claude Code sessions from `~/.claude/projects/`. `DETECTORS` list is the extension point for other harnesses.

- **`sessions.py`**: Local JSON store (`~/.config/sessionbin/sessions.json`) tracking uploaded slugs and delete tokens. Atomic writes with `0600` permissions.

### Key

- **The CLI never parses session files.** Parsing happens server-side. The CLI uploads raw bytes.
- **Delete tokens are stored locally.** The `sessions.json` file is the only record of delete tokens — if lost, the user cannot delete their paste.
- **Server URL resolution has a fixed priority:** `--server` flag > `SESSIONBIN_URL` env var > config file > interactive prompt.

## Running the CLI locally

```bash
uv run --with . sessionbin --help
```

## Commands

```bash
tox -e py313                     # run tests
tox -e lint                      # ruff lint
tox -e lint-fix                  # ruff lint with auto-fix
tox -e check-format              # ruff format check
tox -e format                    # ruff format with auto-fix
tox -e typecheck                 # mypy
```

## Verification

After every code change, run all four checks before reporting the task as done:

```bash
tox -e py313                     # tests
tox -e lint                      # ruff lint
tox -e check-format              # ruff format check
tox -e typecheck                 # mypy
```

Fix any failures before moving on. Do not skip any of these checks.

## Conventions

- Python 3.10+, uv for everything. No `requirements.txt`.
- `ruff` for lint and format. Config in `pyproject.toml`. `mypy` for type checking. `tox` orchestrates all checks.
- Fix lint errors at the source. Don't suppress with `# noqa` or exclude files from linting.
- **No underscore-prefixed "private" function names.** This is an application, not a published library, so there is no external API surface for the convention to protect. Use plain names.
- **Type annotations should describe what the code actually accepts.** If you reach for `typing.cast()` to bridge two things you control, the annotation is wrong — widen or correct it instead. A `cast` on genuinely untyped external data is fine.
- All tests live under `tests/`.
- `pytest` for tests.

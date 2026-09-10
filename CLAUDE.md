# CLAUDE.md

## What is sessionbin

A transcript pastebin for agentic coding sessions. Upload a session file, get a slugged
share URL, anyone with the URL can view the rendered transcript. Anonymous upload,
delete-by-token. **It is a pastebin, not an observability platform** — resist features
that imply accounts, dashboards, or analytics.

Server-rendered HTML, no frontend SPA. HTMX is acceptable for small dynamic bits.

The CLI lives in `cli/` in this repo and has its own CLAUDE.md. It uploads raw bytes and
never parses session files; the HTTP API is the only contract between them.

**The backend and the CLI are two separate uv projects, both distributed as `sessionbin`.**
They cannot share a virtualenv. `tox` handles this (backend envs build the root package,
CLI envs install `./cli`); the dev container installs the CLI with `uv tool install`.
Never point one `UV_PROJECT_ENVIRONMENT` at both — syncing from `cli/` will evict the
backend package from the environment.

## Prerequisite: gitleaks

`gitleaks` must be on `PATH`. `conf/settings/base.py` raises at import time if it is
missing, which takes down the entire pytest suite *and* mypy (django-stubs imports the
settings module to build its plugin) with errors that do not obviously point at gitleaks.

## Architecture

Data flow: raw bytes → redact → adapter → `Session` → render → store fragment. The stored
fragment is embedded in the page shell at serve time.

### Invariants

- **`schema/`, `adapters/`, and `security/` must never import Django.** They are pure
  Python and must stay importable without `DJANGO_SETTINGS_MODULE` set. Nothing enforces
  this.
- **Adapters emit the internal schema, never harness-native shapes.** The renderer must
  never branch on harness. If an adapter cannot represent something, add a schema field.
- **The renderer produces fragments, not pages.** Storage and DB writes belong to the
  service layer.
- **Slugs are the user-facing identity.** Two uploads of the same bytes produce two
  pastes with two slugs. The recorded sha256 is for analytics/dedup and is never exposed.
- **Static assets are versioned.** Bump the version on breaking template changes so old
  stored HTML keeps pointing at the old asset.
- **Rendered fragments are stored, so template changes do not reach existing pastes.**
  After editing `transcript.html`, run `manage.py render` to re-render every stored paste.
- **The deployed image carries no domain.** `deploy/Containerfile` and `settings/prod.py` take
  the hostname from `DJANGO_ALLOWED_HOSTS` at runtime, and `CSRF_TRUSTED_ORIGINS` derives from
  it. Anyone can run their own instance, so never hardcode `sessionbin.dev` outside the CLI's
  overridable `DEFAULT_SERVER_URL`.

## Commands

```bash
uv sync                                                  # backend dependencies
uv run python src/sessionbin/manage.py render [<slug>]   # re-render stored pastes

tox run                    # everything below, in one go
tox run -e py314           # backend tests          tox run -e cli            # CLI tests
tox run -e typecheck       # backend mypy           tox run -e cli-typecheck  # CLI mypy
tox run -e lint            # ruff, both packages    tox run -e check-format   # format check
```

`lint-fix` and `format` are the autofixing variants.

A dev container with the backend, the CLI, gitleaks, and both agent harnesses is in
`dev/` — see the README. Use it when you need a real session file to test against.
**If you add support for a new harness, install it in `dev/Containerfile` too.**

## Verification

Run `tox run` after every code change and fix what fails. Do not skip envs.

For anything touching templates, CSS, upload/delete flows, or API endpoints, also run the
`/e2e-test-runbook` skill against a running dev server.

## Conventions

- Python 3.14+, uv for everything. No `requirements.txt`.
- Fix lint errors at the source. No `# noqa`, no excluding files — migrations get linted
  and formatted like everything else.
- **No underscore-prefixed "private" function names.** This is an application, not a
  published library, so there is no external API surface for the convention to protect.
- **Type annotations should describe what the code actually accepts.** If you reach for
  `typing.cast()` to bridge two things you control, the annotation is wrong — widen or
  correct it. A `cast` on genuinely untyped external data (a settings dict, parsed JSON)
  is fine.
- Tests live under `tests/`. No `tests.py` in app directories. Schema and adapter tests
  are pure Python and run without a database.
- Fixtures are real session files (redacted as needed) under `tests/fixtures/<harness>/`.
  Reproduce an adapter bug with a fixture and a failing test before fixing it.

## Rendering notes

Text and thinking blocks render markdown via `mistune` with `pygments` highlighting.
Tool-use input is highlighted as JSON. **Tool results stay plain `<pre>`** — their output
is arbitrary text, not always JSON.

Pygments emits class-based output, so light (default) and dark (monokai) CSS are both
embedded in the fragment's `<style>` block, keyed to the existing `[data-theme="dark"]`
and `prefers-color-scheme` selectors.

## Session format notes

Reverse-engineered from real files; the fixtures are the ground truth.

### Claude Code (JSONL)

- One JSON object per line, `type` selects the kind. Only `user` and `assistant` become
  turns — `system`, `attachment`, `file-history-snapshot`, `last-prompt`, and
  `permission-mode` are skipped.
- `message.content` is either a plain string (user prompts) or a list of blocks.
- Thinking blocks use the `thinking` key, not `text`.
- Each assistant line carries exactly one content block, so one line is one turn.
- `cwd`, `gitBranch`, and `model` come from the first line that has them. Timestamps are
  ISO 8601 with a `Z` suffix.

### OpenCode (single JSON doc, from `opencode export`)

- Shape is `{"info": {...}, "messages": [...]}` — those two keys are what auto-detection
  keys off.
- Model id is `info.model.id`; working directory is `info.directory` (not `cwd`).
- **Several assistant messages share one `parentID` and are merged into a single turn**,
  unlike Claude Code. A turn's start is the first message's `time.created`; its end is
  the last merged message's `time.completed`, which is why `Turn.ended_at` exists.
- Assistant messages with an `error` key and no parts are skipped.
- Tool parts carry `state.status`; only `completed` and `error` produce a result block.

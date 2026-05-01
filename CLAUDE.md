# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is sessionbin

Sessionbin is a transcript pastebin for agentic coding sessions (Claude Code, Codex, OpenCode, Gemini). Users upload a session file, get a slugged share URL, anyone with the URL can view the server-rendered transcript. Anonymous upload, delete-by-token. Not an observability platform — it's a pastebin.

The site is server-rendered HTML. No frontend SPA. HTMX is acceptable for small dynamic bits if needed.

A separate `sessionbin-cli` repo/package handles the client side. The CLI uploads raw bytes over HTTP and never parses session files — parsing happens server-side. Its only contract with this backend is the HTTP API.

## Architecture

The `schema/` and `adapters/` layers are pure Python — they must never import Django and must be importable without `DJANGO_SETTINGS_MODULE` set. The remaining layers use Django.

- **`schema/`** — Domain dataclasses (`Session`, `Turn`, `Block`). The harness-neutral in-memory representation of a parsed session.
- **`adapters/`** — Parsers that convert raw harness-specific files into `Session` objects. Currently only `claude_code.py` (JSONL → Session). Each adapter exposes a `parse(raw: bytes) -> Session` function. Adapters output the internal schema, not harness-native shapes — the renderer should never branch on harness.
- **`security/`** — Pure Python. Secret redaction via `gitleaks`. `redact.py` exposes `redact_secrets(raw: bytes) -> bytes` which scrubs credentials/tokens from uploaded session files before parsing. Runs as a pre-processing step in the upload pipeline.
- **`storage/`** — Storage abstraction. `base.py` defines the `Storage` protocol, `filesystem.py` implements `FilesystemStorage`, `exceptions.py` defines `StorageError`/`NotFoundError`. `factory.py` reads `settings.SESSIONBIN` to return a configured backend. The rest of the package is pure Python.
- **`pastes/`** — Django app. `models.py` defines the `Paste` model, `services.py` orchestrates parse → render → store on upload, `api.py` is a django-ninja router with the upload endpoint, `views.py` has the paste view and landing page. `render.py` renders `Session` objects to HTML fragments using Django templates. Templates live in `pastes/templates/pastes/`. The `render` management command re-renders stored session files.
- **`conf/`** — Django project settings/urls.

Data flows: raw bytes → redaction → adapter → `Session` → renderer → HTML fragment. The fragment is stored and embedded in Django's page shell at serve time.

### Key invariants

- **No Django imports in `schema/`, `adapters/`, or `security/`.** These layers are pure Python and must work without Django configured.
- **Adapters output the internal schema, never harness-native shapes.** If an adapter can't represent something, the schema needs a new field — don't leak harness-specific data through.
- **Slugs are the user-facing identity.** Two uploads of the same file produce two different pastes with two different slugs. A sha256 is recorded for analytics/dedup but is not user-facing.
- **Renderer produces fragments, not pages.** Storage and DB writes happen in the service layer. Fragments are embedded in the Django page shell (`base.html`) at serve time.
- **Static assets are versioned (`/static/v1/style.css`).** Bump the version on breaking template changes. Old HTML keeps pointing at the old version.

## Commands

```bash
uv sync                                                # install/update dependencies
uv run python src/sessionbin/manage.py render           # re-render all stored pastes
uv run python src/sessionbin/manage.py render <slug>    # re-render a single paste
uv run tox run -e py314                                # run all tests
uv run tox run -e lint                                 # ruff lint
uv run tox run -e check-format                        # ruff format check
uv run tox run -e typecheck                            # mypy
```

## Re-rendering stored pastes

After changing the transcript template (`pastes/templates/pastes/transcript.html`), re-render all stored pastes so they pick up the new markup:

```bash
uv run python src/sessionbin/manage.py render
```

## Verification

After every code change, you MUST run all four checks before reporting the task as done:

```bash
uv run tox run -e py314            # tests
uv run tox run -e lint             # ruff lint
uv run tox run -e check-format    # ruff format check
uv run tox run -e typecheck        # mypy
```

Fix any failures before moving on. Do not skip any of these checks.

For larger changes — anything touching templates, CSS, upload/delete flows, or API endpoints — also run the `/e2e-test-runbook` skill against a running dev server to verify end-to-end functionality in the browser.

## Conventions

- Python 3.14+, uv for everything. No `requirements.txt`.
- `ruff` for lint and format. Config in `pyproject.toml`. `mypy` with `django-stubs` for type checking. `tox` orchestrates all checks.
- Fix lint errors at the source. Don't suppress with `# noqa` or exclude files/directories from linting — auto-generated code (migrations, etc.) gets linted and formatted like everything else.
- All tests live under `tests/`. No `tests.py` in Django app directories.
- `pytest` for tests, `pytest-django` for Django-dependent tests. Schema and adapter tests are pure Python and run without a database.
- Fixtures are real session files (redacted as needed) stored under `tests/fixtures/<harness>/`. Adapter bugs are reproduced by adding a fixture and writing a test before fixing the code.
- Golden-file tests for the renderer: render fixtures, compare against expected HTML, regenerate intentionally.

## Current state

The full upload → parse → render → store → view pipeline works end-to-end. `POST /api/upload` accepts a session JSONL file, parses it with the Claude Code adapter, renders an HTML fragment, writes to filesystem storage, creates a `Paste` DB row, and returns the share URL. `GET /p/<slug>/` serves the rendered transcript embedded in the site's page shell. The landing page at `/` has a web upload form with drag-and-drop. The `manage.py render` command re-renders session files to HTML fragments.

Deletion works via both web and API. `GET /p/<slug>/manage/?token=<delete_token>` shows paste metadata and a delete button. `POST` to the same URL soft-deletes the paste. `DELETE /api/p/<slug>` with `X-Delete-Token` header does the same via API. Soft-delete sets `deleted_at`, removes storage files, keeps the DB record. Deleted pastes return 404 on view.

### URL structure

- `/` — web upload form (GET shows form, POST processes upload and redirects to manage page)
- `/api/upload` — POST, accepts `file` multipart field, returns JSON `{slug, url, delete_token}`
- `/api/p/<slug>` — DELETE, requires `X-Delete-Token` header, returns 204
- `/raw/<slug>.jsonl` — GET, download the original JSONL (served gzip-encoded)
- `/p/<slug>/` — view a paste
- `/p/<slug>/manage/?token=<delete_token>` — manage page (view metadata, delete)
- `/admin/` — Django admin

### Transcript rendering

Text blocks (user and assistant) and thinking blocks render markdown via `mistune` with syntax highlighting via `pygments`. The `render_markdown` template filter in `pastes/templatetags/transcript.py` handles this. Bare URLs are auto-linked (mistune `url` plugin). Tool-use input JSON is syntax-highlighted via the `highlight_json` template filter. Tool-result blocks remain plain `<pre>` (output is arbitrary text, not always JSON).

Pygments uses class-based output. Light theme (default style) and dark theme (monokai) CSS are embedded in the fragment's `<style>` block, keyed to the existing dark mode selectors (`[data-theme="dark"]` and `@media (prefers-color-scheme: dark)`).

### Not yet built
- Adapter auto-detection (hardcoded to Claude Code)
- Adapters for other harnesses (Codex, OpenCode, Gemini)
- Golden-file tests for the renderer

## Claude Code JSONL format notes

The fixtures at `tests/fixtures/claude_code/` are the ground truth for the adapter. Key details discovered during implementation:

- One JSON object per line. `type` field determines the line kind.
- Only `user` and `assistant` types become turns; `system`, `attachment`, `file-history-snapshot`, `last-prompt`, `permission-mode` are skipped.
- `message.content` is either a plain string (user prompts) or a list of content blocks.
- Thinking blocks use the `thinking` key (not `text`).
- Each assistant JSONL line contains exactly one content block (Claude Code streams one block per line).
- Metadata (`cwd`, `gitBranch`, `model`) is pulled from the first line that has it. Timestamps are ISO 8601 with `Z` suffix.

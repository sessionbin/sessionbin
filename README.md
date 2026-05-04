# sessionbin-cli

CLI for uploading and managing [sessionbin](https://sessionbin.dev) transcripts.

## Installation

```bash
uv tool install sessionbin
# or
pip install --user sessionbin
```

## Usage

### Upload a session

Upload a specific file:

```bash
sessionbin upload ~/.claude/projects/-home-user-repos-myproject/abc123.jsonl
```

Or pick from recent Claude Code sessions interactively:

```bash
sessionbin upload
```

Upload the most recent session directly:

```bash
sessionbin upload --latest
```

Use `-y` to skip the confirmation prompt:

```bash
sessionbin upload --latest -y
```

### List uploads

```bash
sessionbin list
```

Shows locally-tracked uploads (URL, filename, upload time).

### Delete an upload

```bash
sessionbin delete <slug>
```

Deletes the paste on the server and removes the local record.

## Configuration

On first run, you'll be prompted for a server URL (defaults to `https://sessionbin.dev`). The choice is saved to `~/.config/sessionbin/config.toml`.

You can override the server URL per-command:

```bash
sessionbin upload --server http://localhost:8000
```

Or via environment variable:

```bash
export SESSIONBIN_URL=http://localhost:8000
```

Priority: `--server` flag > `SESSIONBIN_URL` env var > `config.toml` > interactive prompt.

## Session data

Upload metadata (slugs, delete tokens) is stored in `~/.config/sessionbin/sessions.json` with `0600` permissions. This file is local-only — the `list` command reads from it without contacting the server.

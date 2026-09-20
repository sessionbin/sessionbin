---
name: e2e-test-runbook
description: Use when you need to manually test sessionbin end-to-end — after UI/template changes, API changes, upload/delete flow changes, or before a release. Runs all functional tests in the browser and via curl.
---

# End-to-End Test Runbook

Run all functional tests against the dev container from `dev/`, which serves the mounted checkout at `http://127.0.0.1:8000/`. Uses Playwright MCP for browser tests and curl for API tests.

## Setup

Run everything below from the repo root, on the host. The container mounts the checkout at `/repo`, so edits are live and no rebuild is needed after a code change.

1. Check whether the container is already running:
   ```bash
   podman ps --filter name=sessionbin-dev --format '{{.Names}} {{.Status}}'
   ```

2. If it isn't, build and start it detached:
   ```bash
   podman build -t sessionbin-dev -f dev/Containerfile dev/
   podman run -d --rm -p 8000:8000 -v "$PWD":/repo:Z \
       -v sessionbin-uv-cache:/root/.cache/uv \
       --name sessionbin-dev sessionbin-dev
   ```

3. Wait for it to serve — the entrypoint syncs dependencies, installs the CLI, and migrates first:
   ```bash
   until curl -sf -o /dev/null http://127.0.0.1:8000/; do sleep 2; done
   ```
   If this does not settle within a couple of minutes, read `podman logs sessionbin-dev` and stop.

The database and stored pastes live in `/state` inside the container, so a fresh container starts empty and nothing lands in the checkout.

**Fixture files:** This runbook uses checked-in fixtures only. Do not run `claude`, `codex`, `opencode`, or `pi` inside the container to capture a fresh session — that needs credentials the runbook does not have and must not go looking for. curl runs on the host, so fixture paths are repo-relative. Use fixtures from every harness:
- `tests/fixtures/claude_code/*.jsonl` — Claude Code sessions (JSONL). The two are not
  interchangeable, so each section names the one it needs:
  `f9e8d7c6-b5a4-3210-fedc-ba9876543210.jsonl` runs 22 turns, 4 of them user turns, over
  10m 0s, and is the only one with a navigator worth stepping through;
  `a1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl` is 4 turns with a single user turn, the
  degenerate case for the navigator.
- `tests/fixtures/opencode/*.json` — OpenCode sessions (JSON). Need at least one.
- `tests/fixtures/codex/*.jsonl` — Codex sessions (JSONL rollouts). Need at least one.
- `tests/fixtures/pi/*.jsonl` — Pi sessions (JSONL). Need at least one.

## Test Procedure

Work through each section in order. Record pass/fail for every check. Stop and report on first failure.

### 1. Landing Page

1. Navigate to `http://127.0.0.1:8000/`
2. Take a snapshot and verify:
   - [ ] Page title is "sessionbin"
   - [ ] Heading "sessionbin" is visible
   - [ ] Description text about sharing transcripts is present, mentioning **Claude Code**, **Codex**, **OpenCode**, and **Pi**
   - [ ] Drag-and-drop upload zone with "Drag a file here, or click to browse" text exists
   - [ ] "Upload" button exists
   - [ ] "Upload from the command line" section with per-harness instructions (Claude Code, Codex, OpenCode, Pi) and curl examples exists
   - [ ] Navbar has "sessionbin" link, GitHub link, and theme toggle button
   - [ ] No console errors besides favicon 404

### 2. Theme Toggle

1. Click the "Toggle theme" button
2. Take a screenshot — verify the theme changed (dark ↔ light)
3. Click the "Toggle theme" button again
4. Take a screenshot — verify it toggled back

### 3. Web Upload

1. On the landing page, click the drop zone text to open the file picker
2. Upload `tests/fixtures/claude_code/f9e8d7c6-b5a4-3210-fedc-ba9876543210.jsonl` — the
   multi-turn one, which sections 5 and 5a need
3. Verify the filename appears in the drop zone
4. Click the "Upload" button
5. Verify redirect to manage page (`/p/<slug>/manage/?token=<token>`)
6. **Save the slug and token** for later tests

### 4. Manage Page

The page is the moment of success for a web upload, so it leads with the share link, not
with deleting.

1. On the manage page from step 3, take a snapshot and verify:
- [ ] Page title includes "Manage" and the slug
- [ ] Heading is "Transcript uploaded"
- [ ] A summary line under it reports what was parsed, joined by `·`: harness, model,
      turn count, tool call count — for this fixture,
      `claude-code · claude-sonnet-4-20250514 · 22 turns · 8 tool calls`
- [ ] Under "Share link", the **absolute** URL is shown as text, `http://127.0.0.1:8000/p/<slug>/`,
      not the relative path — selecting it by hand yields something shareable
- [ ] A "View transcript" button follows it
- [ ] A notice says this page is the only way to delete the paste and cannot be recovered,
      and shows the manage URL with its own Copy button
- [ ] The slug and upload timestamp appear in a muted line
- [ ] "Delete this paste" is a quiet outlined button at the foot of the page, not a filled
      red one, with its warning text beside it
2. Narrow the window to 390px and verify neither URL overflows the page and the delete
   row wraps rather than scrolling sideways
3. Click the Copy button beside the share link. Verify it reads "Copied" for about a
   second, then returns to "Copy", and that the clipboard holds the absolute paste URL:
   ```js
   navigator.clipboard.readText()
   ```
4. Do the same for the Copy button on the manage URL, and verify the clipboard holds the
   full manage URL including `?token=`
5. Copy the share link and then the manage link a moment later. Verify each button keeps
   its own "Copied" for its own second: the first timer must not wipe the second's
   confirmation early
6. A copy can fail, and this page must say so rather than doing nothing — it is the only
   copy of the manage URL that will ever exist. Load the same manage page over the host's
   LAN IP rather than `127.0.0.1`, which is an insecure context where
   `navigator.clipboard` is undefined, and click a Copy button. Verify:
   - [ ] A red "Copy failed — select the link and copy it yourself." appears under the URL
   - [ ] It stays put rather than clearing after a second
   - [ ] The button still reads "Copy", so nothing claims a copy that did not happen

### 5. Paste View

1. Click the "View transcript" button on the manage page
2. Take a screenshot and verify:
   - [ ] Page title includes the slug
   - [ ] Session metadata header shows: harness name, model, start time, duration, turn count, tool call count
   - [ ] No per-turn model labels: this session used one model, so only the header names it
   - [ ] User turns have "user" label with timestamp
   - [ ] Assistant turns have "assistant" label with timestamp
   - [ ] Text content blocks render inside the turns
   - [ ] Tool-use blocks render with collapsed/expandable summaries
   - [ ] Tool-result blocks render with collapsed/expandable summaries
   - [ ] Duration reads in hours once past one, e.g. `10m 0s` here but `7h 3m` on a
         long session, never `423m 38s`

### 5a. Turn Navigator

The header carries an index of the session's **user** turns: `« ‹ N / M ▾ › »`. Its
position readout cannot always be derived from the scroll position, so check the
behaviour, not just that the controls are on screen.

On the paste from step 5, verify:
- [ ] The navigator is present, and `M` equals the number of `user` turns in the
      transcript, not the total turn count in the header: `4`, not `22`
- [ ] Opening `▾` lists every user turn with its timestamp, each a link to `#turn-<n>`
- [ ] Clicking an entry scrolls to that turn, flashes it, closes the panel, and moves
      the readout to that entry
- [ ] `›` and `‹` step one turn at a time; `»` and `«` jump to the ends
- [ ] At the first turn `«` and `‹` are dimmed; at the last, `›` and `»` are. A dimmed
      control still shows its tooltip on hover
- [ ] Scrolling by hand from top to bottom moves the readout forwards only, reaching
      `M / M` at the foot of the page
- [ ] After jumping to a turn, scrolling away by **dragging the scrollbar** (no wheel,
      no keys) releases the choice and the readout follows the page again
- [ ] Loading `/p/<slug>/#turn-<n>` for an indexed turn selects that entry; going Back
      to the bare URL returns the readout to `1 / M`
- [ ] Once scrolled, the header sticks to the top, compacts, drops the absolute date
      and casts a shadow; turns pass underneath it rather than colliding with it

### 5b. Tooltips

Tooltips are drawn by the page, not the browser, and are *warmed*: slow the first time,
instant for a short window afterwards.

- [ ] Hovering a navigator control shows a tooltip after a short pause, styled like the
      page rather than an OS tooltip
- [ ] Leaving and immediately hovering a neighbouring control shows its tooltip at once
- [ ] Waiting a second or so and hovering again brings the pause back
- [ ] Hovering a turn timestamp shows the full UTC timestamp; hovering the word
      `thinking` on an omitted-reasoning row shows its explanation, positioned under the
      word rather than the middle of the page
- [ ] The GitHub link and theme toggle in the navbar both have tooltips
- [ ] No element in the page still carries a `title` attribute, so the browser's own
      tooltip never doubles up:
      ```js
      document.querySelectorAll('[title]').length   // expect 0
      ```

### 6. API Upload

1. Use curl to upload the other Claude Code fixture:
   ```
   curl -s -F "file=@tests/fixtures/claude_code/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl" http://127.0.0.1:8000/api/upload
   ```
2. Verify response is JSON with fields: `slug`, `url`, `delete_token`
3. **Save the slug and delete_token** for the API delete test
4. Navigate to the returned `url` in the browser and verify the paste renders
5. This fixture holds a single user turn, which is the degenerate case for the
   navigator. Verify:
   - [ ] The readout is `1 / 1`
   - [ ] All four stepper arrows are hidden, not merely dimmed — with one turn there is
         nothing to step between

### 7. API Delete

1. Delete the paste from step 6 using curl:
   ```
   curl -s -o /dev/null -w "%{http_code}" -X DELETE \
     -H "X-Delete-Token: <delete_token>" \
     http://127.0.0.1:8000/api/p/<slug>
   ```
2. Verify response status is **204**
3. Verify the paste now returns **404**:
   ```
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/p/<slug>/
   ```

### 8. Web Delete

1. Navigate to the manage page for the paste from step 3 (using the saved slug and token)
2. Click "Delete this paste"
3. Take a snapshot and verify:
   - [ ] Heading now reads "Paste deleted"
   - [ ] The share link is replaced with "(deleted)" in italics/emphasis, and the
         "View transcript" button is gone
   - [ ] The manage URL notice about losing delete rights is gone
   - [ ] The harness/model/turns summary line is gone: it described content that no
         longer exists
   - [ ] A deletion timestamp message appears (e.g., "This paste was deleted on ...")
   - [ ] The delete button is gone
4. Verify the paste view now returns **404**:
   ```
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/p/<slug>/
   ```

### 9. OpenCode Upload (API)

1. Use curl to upload an OpenCode fixture:
   ```
   curl -s -F "file=@tests/fixtures/opencode/agents_md_symlink.json" http://127.0.0.1:8000/api/upload
   ```
2. Verify response is JSON with fields: `slug`, `url`, `delete_token`
3. Navigate to the returned `url` in the browser
4. Take a screenshot and verify:
   - [ ] Session metadata header shows **"opencode"** as the harness name
   - [ ] Model name is displayed (e.g., "claude-sonnet-4-6@default")
   - [ ] User turn renders with the prompt text
   - [ ] Assistant turn renders with tool-use blocks (read, write, bash) and tool-result blocks
   - [ ] Final assistant text response is visible
5. **Save the slug** and delete the paste to clean up:
   ```
   curl -s -o /dev/null -w "%{http_code}" -X DELETE \
     -H "X-Delete-Token: <delete_token>" \
     http://127.0.0.1:8000/api/p/<slug>
   ```

### 10. OpenCode Upload with Harness Parameter

1. Upload an OpenCode fixture with the explicit `harness` query parameter:
   ```
   curl -s -F "file=@tests/fixtures/opencode/basic_addition.json" "http://127.0.0.1:8000/api/upload?harness=opencode"
   ```
2. Verify response is JSON with `slug`, `url`, `delete_token`
3. Navigate to the paste and verify it renders with **"opencode"** harness in the header
4. Clean up by deleting the paste

### 11. Invalid Harness Parameter

1. Upload with an invalid harness value:
   ```
   curl -s -w "\n%{http_code}" -F "file=@tests/fixtures/claude_code/f9e8d7c6-b5a4-3210-fedc-ba9876543210.jsonl" "http://127.0.0.1:8000/api/upload?harness=bogus"
   ```
2. Verify response status is **400**
3. Verify response JSON contains `"error"` field mentioning "unknown harness"

### 12. OpenCode Web Upload

1. Navigate to `http://127.0.0.1:8000/`
2. Upload an OpenCode fixture file (`.json` from `tests/fixtures/opencode/`) via the drop zone
3. Click "Upload"
4. Verify redirect to manage page
5. Click "View transcript" and verify the paste renders with **"opencode"** harness
6. Clean up by deleting the paste via the manage page

### 13. Codex Upload (API)

1. Use curl to upload a Codex fixture without a harness parameter, so auto-detection is exercised:
   ```
   curl -s -F "file=@tests/fixtures/codex/rollout-2026-09-14T10-20-48-01a0a04a-bfb2-7e12-8e42-9bdd2783d9d2.jsonl" http://127.0.0.1:8000/api/upload
   ```
2. Verify response is JSON with fields: `slug`, `url`, `delete_token`
3. Navigate to the returned `url` in the browser
4. Take a screenshot and verify:
   - [ ] Session metadata header shows **"codex"** as the harness name
   - [ ] Header lists both models the session used, joined by `·`: **gpt-5.6-luna · gpt-5.6-sol**
   - [ ] Every turn carries its own model label, which only appears when a session used more
         than one model
   - [ ] Two user prompts render (the second was a resumed turn)
   - [ ] `exec` tool-use blocks and their result blocks render collapsed
   - [ ] Blank reasoning collapses to a one-line "thinking" row, not an empty card
   - [ ] Final assistant text response is visible
5. Clean up by deleting the paste via the API

### 14. Codex Web Upload

1. Navigate to `http://127.0.0.1:8000/`
2. Upload a Codex fixture file (`.jsonl` from `tests/fixtures/codex/`) via the drop zone
3. Click "Upload"
4. Verify redirect to manage page
5. Click "View transcript" and verify the paste renders with **"codex"** harness
6. Clean up by deleting the paste via the manage page

### 15. Pi Upload (API)

1. Use curl to upload a Pi fixture without a harness parameter, so auto-detection is exercised:
   ```
   curl -s -F "file=@tests/fixtures/pi/2026-09-14T17-00-47-986Z_01a0a0dd-39f2-73ea-ab16-e09dcdd32d87.jsonl" http://127.0.0.1:8000/api/upload
   ```
2. Verify response is JSON with fields: `slug`, `url`, `delete_token`
3. Navigate to the returned `url` in the browser
4. Take a screenshot and verify:
   - [ ] Session metadata header shows **"pi"** as the harness name
   - [ ] Model name is displayed (e.g., "qwen38")
   - [ ] One user prompt renders
   - [ ] `read`, `write`, and `bash` tool-use blocks and their result blocks render collapsed
   - [ ] The `read` result is marked as an error (ENOENT)
   - [ ] Thinking blocks render collapsed with a one-line preview
   - [ ] Final assistant text response is visible
5. Clean up by deleting the paste via the API

### 16. Pi Web Upload

1. Navigate to `http://127.0.0.1:8000/`
2. Upload a Pi fixture file (`.jsonl` from `tests/fixtures/pi/`) via the drop zone
3. Click "Upload"
4. Verify redirect to manage page
5. Click "View transcript" and verify the paste renders with **"pi"** harness
6. Clean up by deleting the paste via the manage page

### 17. Error Handling (unchanged from Claude Code tests)

Run these curl checks and verify the expected status codes:

1. **Non-existent paste → 404:**
   ```
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/p/nonexistent/
   ```

2. **Wrong delete token → 404:**
   ```
   curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/p/<slug>/manage/?token=wrongtoken"
   ```

3. **Upload with no file → 422:**
   ```
   curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8000/api/upload
   ```

4. **Delete with wrong token → 404:**
   ```
   curl -s -o /dev/null -w "%{http_code}" -X DELETE \
     -H "X-Delete-Token: wrongtoken" \
     http://127.0.0.1:8000/api/p/<any-valid-slug>
   ```

## Teardown

Only if this runbook started the container (step 2 of Setup), stop it:

```bash
podman stop sessionbin-dev
```

It runs with `--rm`, so the database and any pastes left behind by a failed run go with it. Leave a container that was already running alone.

## Results

After all sections pass, report a summary table:

| Test | Result |
|------|--------|
| Landing page | |
| Theme toggle | |
| Web upload | |
| Manage page | |
| Paste view | |
| Turn navigator | |
| Tooltips | |
| API upload | |
| API delete | |
| Web delete | |
| OpenCode upload (API) | |
| OpenCode upload with harness param | |
| Invalid harness parameter | |
| OpenCode web upload | |
| Codex upload (API) | |
| Codex web upload | |
| Pi upload (API) | |
| Pi web upload | |
| Error handling | |

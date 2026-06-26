---
name: e2e-test-runbook
description: Use when you need to manually test sessionbin end-to-end — after UI/template changes, API changes, upload/delete flow changes, or before a release. Runs all functional tests in the browser and via curl.
---

# End-to-End Test Runbook

Run all functional tests against a running local dev server at `http://127.0.0.1:8000/`. Uses Playwright MCP for browser tests and curl for API tests.

**Prerequisite:** The dev server must be running. If it isn't, start it:
```
uv run python src/sessionbin/manage.py runserver
```

**Fixture files:** Use fixtures from both harnesses:
- `tests/fixtures/claude_code/*.jsonl` — Claude Code sessions (JSONL). Need at least two (one for web upload, one for API upload).
- `tests/fixtures/opencode/*.json` — OpenCode sessions (JSON). Need at least one.

## Test Procedure

Work through each section in order. Record pass/fail for every check. Stop and report on first failure.

### 1. Landing Page

1. Navigate to `http://127.0.0.1:8000/`
2. Take a snapshot and verify:
   - [ ] Page title is "sessionbin"
   - [ ] Heading "sessionbin" is visible
   - [ ] Description text about sharing transcripts is present, mentioning **Claude Code** and **OpenCode**
   - [ ] Drag-and-drop upload zone with "Drag a file here, or click to browse" text exists
   - [ ] "Upload" button exists
   - [ ] "Upload from the command line" section with per-harness instructions (Claude Code, OpenCode) and curl examples exists
   - [ ] Navbar has "sessionbin" link, GitHub link, and theme toggle button
   - [ ] No console errors besides favicon 404

### 2. Theme Toggle

1. Click the "Toggle theme" button
2. Take a screenshot — verify the theme changed (dark ↔ light)
3. Click the "Toggle theme" button again
4. Take a screenshot — verify it toggled back

### 3. Web Upload

1. On the landing page, click the drop zone text to open the file picker
2. Upload a fixture file (first `.jsonl` from `tests/fixtures/claude_code/`)
3. Verify the filename appears in the drop zone
4. Click the "Upload" button
5. Verify redirect to manage page (`/p/<slug>/manage/?token=<token>`)
6. **Save the slug and token** for later tests

### 4. Manage Page

On the manage page from step 3, take a snapshot and verify:
- [ ] Page title includes "Manage" and the slug
- [ ] Heading is "Manage paste"
- [ ] Metadata shows: Slug, Uploaded timestamp, Size (in bytes), View URL
- [ ] View URL is a link to `/p/<slug>/`
- [ ] "Delete this paste" button is present
- [ ] Delete warning text is present

### 5. Paste View

1. Click the View URL link on the manage page
2. Take a screenshot and verify:
   - [ ] Page title includes the slug
   - [ ] Session metadata header shows: harness name, model, CWD, branch, start time, duration, turn count, tool call count
   - [ ] User turns have "user" label with timestamp
   - [ ] Assistant turns have "assistant" label with timestamp
   - [ ] Text content blocks render inside the turns
   - [ ] Tool-use blocks render with collapsed/expandable summaries
   - [ ] Tool-result blocks render with collapsed/expandable summaries

### 6. API Upload

1. Use curl to upload a second fixture file:
   ```
   curl -s -F "file=@tests/fixtures/claude_code/<second-file>.jsonl" http://127.0.0.1:8000/api/upload
   ```
2. Verify response is JSON with fields: `slug`, `url`, `delete_token`
3. **Save the slug and delete_token** for the API delete test
4. Navigate to the returned `url` in the browser and verify the paste renders

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
   - [ ] View URL is replaced with "(deleted)" in italics/emphasis
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
5. Click the View URL and verify the paste renders with **"opencode"** harness
6. Clean up by deleting the paste via the manage page

### 13. Error Handling (unchanged from Claude Code tests)

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

## Results

After all sections pass, report a summary table:

| Test | Result |
|------|--------|
| Landing page | |
| Theme toggle | |
| Web upload | |
| Manage page | |
| Paste view | |
| API upload | |
| API delete | |
| Web delete | |
| OpenCode upload (API) | |
| OpenCode upload with harness param | |
| Invalid harness parameter | |
| OpenCode web upload | |
| Error handling | |

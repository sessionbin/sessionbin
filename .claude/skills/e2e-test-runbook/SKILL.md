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

**Fixture files:** `tests/fixtures/claude_code/*.jsonl` — use whichever are available. You need at least two distinct files (one for web upload, one for API upload).

## Test Procedure

Work through each section in order. Record pass/fail for every check. Stop and report on first failure.

### 1. Landing Page

1. Navigate to `http://127.0.0.1:8000/`
2. Take a snapshot and verify:
   - [ ] Page title is "sessionbin"
   - [ ] Heading "sessionbin" is visible
   - [ ] Description text about sharing transcripts is present
   - [ ] Drag-and-drop upload zone with "Drag a file here, or click to browse" text exists
   - [ ] "Upload" button exists
   - [ ] "Upload from the command line" section with curl/httpie examples exists
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

### 9. Error Handling

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
| Error handling | |

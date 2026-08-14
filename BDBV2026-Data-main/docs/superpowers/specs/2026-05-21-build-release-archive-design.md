# Build release & archive workflow — design

**Date:** 2026-05-21
**Status:** approved (design); implementation pending
**Touches:** `tools/release.py` (new), `tools/lib/release.py` (new), `tools/build_geojson.py`, `build/manifest.json`, `build/DESCRIPTION.md` (new), `README.md`, `.gitignore`

## Goal

Add a dedicated "publish a release" workflow on top of the existing build pipeline. Each release:

1. Archives the *previous* `build/` (plus the QA logs that backed it) as a versioned GitHub Release asset.
2. Regenerates `build/` from current data.
3. Captures a short human-written "what's new and why" description for the new build, which travels with the build into its eventual archive.
4. Updates `README.md` so casual visitors see the current build's description and a log of past releases.

`python -m tools.build_geojson` stays the dev-iteration tool (no archive, no release, no README rewrite). `python -m tools.release` is the explicit maintainer ritual for cutting a new public snapshot.

## Non-goals

- Auto-publishing on every CI build or every merge to `main`. Releases are deliberately maintainer-triggered.
- Tracking semantic versions. Tags are date+sha; users who care about version semantics use the description.
- Storing build archives inside the repo. Archives live on GitHub Releases.
- Restoring an old build into `build/`. Consumers download the tarball directly from the GitHub Releases page (or via `gh release download`); we don't ship a "checkout build X" command.

## Architecture

### New files

- **`tools/release.py`** — orchestrator entry point (`python -m tools.release`). Sequences preflight → archive → rebuild → prompt → README update. Holds the only I/O coupling (subprocess for `gh`, `git`, `$EDITOR`).
- **`tools/lib/release.py`** — pure helpers, no subprocess or filesystem side effects beyond what callers pass in:
  - `build_tag(date: str, short_sha: str) -> str` → `"build-2026-05-21-396cf8a"`
  - `pack_archive(paths: list[Path], out: Path) -> None` → writes a `.tar.gz`
  - `render_editor_template() -> str` → returns the pre-filled editor buffer
  - `strip_editor_comments(raw: str) -> str` → drops `#`-prefixed lines, trims
  - `rewrite_readme(readme: str, *, last_build_line: str, current_date: str, whats_new: str, past_release_row: str) -> str` → returns the new README text; idempotent between markers
  - All unit-testable.

### Modified files

- **`tools/build_geojson.py`** — `main()` writes two new keys into `build/manifest.json`:
  - `"built_at"` — ISO 8601 timestamp of the build
  - `"commit"` — short SHA of `git rev-parse --short HEAD` at build time
  These are needed at the *next* release run to construct the archive tag for the *previous* build. Without them, we'd have to guess.
- **`README.md`** — gains:
  - Two HTML-comment marker pairs so `rewrite_readme` is idempotent and tolerant of nearby edits:
    - `<!-- whats-new:start -->` … `<!-- whats-new:end -->` inside the existing `# Current build` section
    - `<!-- past-releases:start -->` … `<!-- past-releases:end -->` for the new "## Past releases" table
  - Updated **Contributor flow** with a release step (details below).
- **`.gitignore`** — add `dist/` (temp tarball staging).

### New committed artifact

- **`build/DESCRIPTION.md`** — single-file "what's new and why" for the build currently in `build/`. Committed alongside the build outputs. On the next release, its contents become the GitHub Release notes for the archive.

## Detailed flow

`python -m tools.release` runs the following steps in order. Any failure short-circuits with a clear error and zero side effects beyond steps already completed (see "Failure handling" below).

### 1. Preflight

- `qa/qa_log.csv` exists; zero rows have `status=fail`. Else: `"Run `python -m tools.qa` and resolve failures first."`
- `gh --version` succeeds and `gh auth status` reports a logged-in account with push access to the repo. Else: print install/auth instructions.
- `git status --porcelain` shows no dirty paths *outside* the allowlist `{build/**, qa/qa_log.csv, qa/matrix_log.csv, README.md}`. Else: `"Working tree has unrelated uncommitted changes: <paths>. Commit or stash them first."`
- `git rev-parse --short HEAD` returns a valid SHA (not a fresh repo with no commits).

### 2. Archive the previous build

Skipped on the *first ever* release when `build/DESCRIPTION.md` does not exist (no prior build has been described). In that case, jump straight to step 3.

Otherwise:

- Read `build/manifest.json`. Extract `built_at` (→ date prefix `YYYY-MM-DD`) and `commit` (→ short sha suffix). Build tag = `build-YYYY-MM-DD-<sha>`.
- `gh release view <tag>` → if it exists, refuse: `"Release <tag> already exists; previous build was already archived. Did the rebuild step fail last time?"`
- Pack into `dist/<tag>.tar.gz` (creating `dist/` if missing):
  - `build/drc_health_zones.geojson`
  - `build/long/` (recursive)
  - `build/manifest.json`
  - `build/DESCRIPTION.md`
  - `qa/qa_log.csv`
  - `qa/matrix_log.csv`
- `gh release create <tag> dist/<tag>.tar.gz --title <tag> --notes-file build/DESCRIPTION.md`. Capture the release URL from `gh`'s output for use in step 5.

### 3. Rebuild

- Import and call `tools.build_geojson.main()` in-process (not subprocess — we want to share Python state and avoid swallowing tracebacks).
- On non-zero return: bail. The release published in step 2 stands and accurately describes the old build, which is still intact in `build/` (the rebuild was the thing that failed).
- `build/manifest.json` now carries fresh `built_at` and `commit` written by the modified `build_geojson.main()`.

### 4. Prompt for the new description

- Open `$EDITOR` (default `vi`) on a temp file pre-populated with:
  ```
  # Lines starting with '#' are ignored.
  # Describe what's new in this build and why.
  # First line = short summary (shown in README's Past releases log).
  # Following paragraphs = full release notes (shown on GitHub Releases).

  ```
- After save: strip `#`-prefixed lines, trim trailing whitespace.
- If the result is empty: refuse with `"Description is required."` and re-open the editor (one retry, then bail).
- Write result to `build/DESCRIPTION.md`.

### 5. Update `README.md`

Programmatic rewrite using `rewrite_readme()`:

- Replace line 13's `Last successful build:` with the new timestamp (`built_at` from manifest) and short sha.
- Replace the `# Current build (YYYY-MM-DD)` heading date with the build date.
- Replace the contents of `<!-- whats-new:start -->...<!-- whats-new:end -->` with the new `DESCRIPTION.md` body, prefixed by `**What's new:**` heading.
- Prepend a row to the table inside `<!-- past-releases:start -->...<!-- past-releases:end -->`:

  ```
  | Tag | Date | Summary | Download |
  |-----|------|---------|----------|
  | build-2026-05-21-396cf8a | 2026-05-21 | <first line of previous DESCRIPTION.md> | [release](https://github.com/.../releases/tag/build-2026-05-21-396cf8a) |
  ```

  Newest at top.

### 6. Final output

Print:
```
✓ Archived previous build as <tag> → <release URL>
✓ Rebuilt build/ (N features, M KB)
✓ Updated README.md and build/DESCRIPTION.md

Next: review the changes, then
  git add build/ qa/qa_log.csv qa/matrix_log.csv README.md
  git commit -m "New build YYYY-MM-DD"
  git push
```

We do **not** auto-commit or auto-push. The maintainer reviews and bundles with any related changes.

## Failure handling

Each step is designed to either succeed or leave the repo in a state that's identical-or-better than where it started, plus printed instructions:

- **Preflight fails** → no side effects.
- **Archive fails** (network, auth, tag collision) → no side effects; print the underlying `gh` error.
- **Rebuild fails after archive succeeds** → the release in step 2 stands. `build/` is potentially partially written by `build_geojson`; rerunning `tools.build_geojson` (or `tools.release` after fixing the underlying issue) will recover. The user is told this.
- **Editor produces empty output** → one retry, then bail. `build/DESCRIPTION.md` is left empty/missing; next `tools.release` run will treat it as "first-ever" and skip archival until a description exists.
- **README rewrite fails** (marker missing, IO error) → print the new content to stdout so the user can paste it manually; bail. The release and rebuild stand.

## README contributor-flow updates

Step 0 gains:
```
- gh CLI installed and authenticated (`gh auth login`) — required for cutting releases
- $EDITOR environment variable set (used by `tools.release` for the description prompt)
```

A new **step 6** is added after "Open a PR" / merge:

```
6. Publishing a release (maintainer task). After a merge to `main` introduces
   changes worth a new public snapshot:

   .venv/bin/python -m tools.release

   This will:
   - archive the current `build/` as a GitHub Release tagged `build-YYYY-MM-DD-<sha>`
   - rebuild from current data
   - open $EDITOR to capture a "what's new" description for the new build
   - update README.md (current-build pointers + Past releases log)

   Then `git add build/ qa/*.csv README.md && git commit && git push` to land
   the new build alongside its description.

   Use `tools.build_geojson` (not `tools.release`) for normal local iteration —
   `tools.release` is only for cutting versioned snapshots.
```

## Open questions

None at this point — all design choices have been made:

- Storage: **GitHub Releases** (not in-repo, not LFS)
- Trigger: **separate `tools.release` command** (not flag on build_geojson, not every-build)
- Versioning: **`build-YYYY-MM-DD-<short_sha>`**
- Description input: **`$EDITOR`** with pre-filled template
- Archive contents: **build/ + qa/ logs + DESCRIPTION.md sidecar**
- Description shape: **single "what's new" field** (state is already in manifest.json)
- README updates: **current pointers + Past releases table, between idempotent markers**

## Testing strategy

- `tools/lib/release.py` is pure — unit test `build_tag`, `rewrite_readme`, `strip_editor_comments`, `pack_archive` (the last with a temp dir).
- `tools/release.py` orchestration: integration test that fakes `gh` (via a stub on `$PATH`) and `$EDITOR` (point at a script that writes a fixed buffer), runs in a tmp git repo seeded with a minimal `build/`, asserts archive file is created with expected contents and README is rewritten between markers.
- No end-to-end test against real GitHub Releases — that's a manual smoke step the first time the workflow is used.

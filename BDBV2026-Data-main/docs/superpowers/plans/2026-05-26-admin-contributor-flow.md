# Admin / Contributor Flow Separation + Automated Releases — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the workflow into explicit contributor vs admin roles, eliminate built-artifact merge conflicts on PRs, and replace the manual `tools.release` ritual with a CI-driven release-on-data-merge workflow.

**Architecture:** Contributors PR only `data/**` (+ tests/docs). Admins review and merge. A new GitHub Actions workflow runs on `push` to `main` with `paths: ['data/**']`, extracts the release description from the merge PR body, runs QA + build + publish, then commits `build/`, `qa/`, `README.md` back with `[skip release]`. `tools.release` is reworked to publish the *current* `build/` (the workflow rebuilds it just before calling release), with non-interactive flags for CI use.

**Tech Stack:** Python 3.12, pytest, GitHub Actions, `gh` CLI, Git LFS.

**Reference spec:** `docs/superpowers/specs/2026-05-26-admin-contributor-flow-design.md`

---

## File Map

**Create:**
- `.github/pull_request_template.md` — PR template with `## What's new` section + contributor checklist
- `.github/workflows/release.yml` — release-on-data-merge workflow
- `tests/test_extract_whats_new.py` — unit tests for the description-extraction helper

**Modify:**
- `tools/lib/release.py` — add `extract_whats_new()` pure helper
- `tools/release.py` — drop `_archive_previous_build`, drop trailing rebuild, drop `DESCRIPTION.md` writes, add `--description-file` + `--non-interactive` flags, rewrite `main()` to publish the *current* build
- `tests/test_release_orchestrator.py` — update existing tests for the new orchestrator shape; add CI-mode tests
- `README.md` — split into `# Contributor flow` + `# Admin flow` + `# Release internals`

**Unchanged but referenced:**
- `tools/qa.py`, `tools/build_geojson.py` — invoked by the workflow but no source changes
- `.github/workflows/qa.yml` — PR-validation workflow stays as-is (already path-filtered correctly)

---

## Task 1: `extract_whats_new` pure helper

**Files:**
- Modify: `tools/lib/release.py` (append a new function)
- Create: `tests/test_extract_whats_new.py`

This is the function the workflow uses to pull the release description out of a PR body.

- [ ] **Step 1: Write failing tests**

Create `tests/test_extract_whats_new.py`:

```python
"""Unit tests for tools.lib.release.extract_whats_new."""

import pytest

from tools.lib.release import extract_whats_new


def test_extracts_section_between_headers():
    body = (
        "## Summary\n\nsome stuff\n\n"
        "## What's new\n\n"
        "Updated INSP sitrep through report 011.\n\n"
        "## Contributor checklist\n\n- [x] foo\n"
    )
    assert extract_whats_new(body) == "Updated INSP sitrep through report 011."


def test_extracts_when_section_is_last():
    body = "## Foo\n\nbar\n\n## What's new\n\nThe new stuff.\n"
    assert extract_whats_new(body) == "The new stuff."


def test_strips_html_comments_from_template():
    body = (
        "## What's new\n\n"
        "<!-- This section becomes the GitHub Release description. -->\n"
        "<!-- Write 1–3 sentences. -->\n"
        "Refreshed cross-border data.\n\n"
        "## Next\n"
    )
    assert extract_whats_new(body) == "Refreshed cross-border data."


def test_handles_crlf_line_endings():
    body = "## What's new\r\n\r\nLine one.\r\n\r\n## End\r\n"
    assert extract_whats_new(body) == "Line one."


def test_raises_when_section_missing():
    with pytest.raises(ValueError, match="What's new"):
        extract_whats_new("## Summary\n\nno relevant section\n")


def test_raises_when_section_empty():
    body = "## What's new\n\n<!-- only a comment -->\n\n## End\n"
    with pytest.raises(ValueError, match="empty"):
        extract_whats_new(body)


def test_preserves_multiline_content():
    body = (
        "## What's new\n\n"
        "Line one.\n\n"
        "Line two with **bold** and a [link](https://example.com).\n\n"
        "## Next\n"
    )
    expected = (
        "Line one.\n\n"
        "Line two with **bold** and a [link](https://example.com)."
    )
    assert extract_whats_new(body) == expected
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv/bin/python -m pytest tests/test_extract_whats_new.py -v`
Expected: all 7 tests FAIL with `ImportError: cannot import name 'extract_whats_new'`.

- [ ] **Step 3: Implement `extract_whats_new` in `tools/lib/release.py`**

Append to `tools/lib/release.py`:

```python
WHATS_NEW_HEADER_RE = re.compile(r"^##\s+What's new\s*$", re.MULTILINE)
NEXT_HEADER_RE = re.compile(r"^##\s+", re.MULTILINE)


def extract_whats_new(pr_body: str) -> str:
    """Return the trimmed content of the `## What's new` section of a PR body.

    Strips HTML comments (`<!-- ... -->`) and surrounding whitespace. Raises
    ValueError if the section header is missing or the resulting content is
    empty after stripping comments and whitespace.
    """
    body = pr_body.replace("\r\n", "\n")
    header = WHATS_NEW_HEADER_RE.search(body)
    if header is None:
        raise ValueError("PR body missing `## What's new` section")
    after = body[header.end():]
    next_header = NEXT_HEADER_RE.search(after)
    section = after[: next_header.start()] if next_header else after
    section = re.sub(r"<!--.*?-->", "", section, flags=re.DOTALL)
    section = section.strip()
    if not section:
        raise ValueError("`## What's new` section is empty after stripping comments")
    return section
```

- [ ] **Step 4: Verify tests pass**

Run: `.venv/bin/python -m pytest tests/test_extract_whats_new.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Run the rest of the suite to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS (we have not yet changed `tools.release` orchestration; existing release-orchestrator tests still describe the old behavior — they should all still pass at this point).

- [ ] **Step 6: Commit**

```bash
git add tools/lib/release.py tests/test_extract_whats_new.py
git commit -m "Add extract_whats_new helper for parsing PR-body release descriptions"
```

---

## Task 2: Rework `tools.release` — new CLI flags, drop archive/rebuild/DESCRIPTION.md

**Files:**
- Modify: `tools/release.py`
- Modify: `tests/test_release_orchestrator.py`

This is the substantive Python change. The new orchestrator:

- Adds CLI flags `--description-file <path>` and `--non-interactive`.
- Drops `_archive_previous_build` (entire function removed).
- Drops the trailing `tools.build_geojson` rebuild call.
- Stops writing `build/DESCRIPTION.md`.
- `main()` shape: preflight → resolve description (file or `$EDITOR`) → derive tag from current `build/manifest.json` → `pack_archive` → `gh release create` → update README (the *just-created* release becomes the top row of the past-releases table) → print next steps.

- [ ] **Step 1: Rewrite the orchestrator tests for the new behavior**

Open `tests/test_release_orchestrator.py`. Replace the file contents with the version below. Key changes vs the current file:

- `_seed_repo` no longer writes `build/DESCRIPTION.md` (parameter removed).
- The fake `gh` no longer needs the `release view` early-exit (no precheck).
- The bootstrap no longer fakes `tools.build_geojson` (orchestrator does not call it).
- New tests for `--description-file` and `--non-interactive`.
- Happy-path test asserts: archive packed at `dist/<tag>.tar.gz`, `gh release create` invoked with the *current* manifest's tag, README rewritten with that tag in past-releases, no `build/DESCRIPTION.md` written.

```python
"""Integration tests for the tools.release orchestrator (new flow).

Stubs `gh` (PATH manipulation) and `$EDITOR` (env var). The orchestrator no
longer rebuilds — the workflow does that before calling tools.release — so
tests do not fake tools.build_geojson.
"""

import json
import os
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


README_TEMPLATE = (
    "# Header\n\n"
    "Last successful build: **OLD** (commit `oldsha`).\n\n"
    "# Current build (2026-01-01)\n\n"
    "prose\n\n"
    "<!-- whats-new:start -->\n"
    "old description\n"
    "<!-- whats-new:end -->\n\n"
    "## Past releases\n\n"
    "<!-- past-releases:start -->\n"
    "| Tag | Date | Summary | Download |\n"
    "|-----|------|---------|----------|\n"
    "<!-- past-releases:end -->\n\n"
    "# Repository layout\n"
)


def _make_stub(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _seed_repo(tmp: Path) -> None:
    (tmp / "build").mkdir()
    (tmp / "build" / "long").mkdir()
    (tmp / "build" / "drc_health_zones.geojson").write_text(
        '{"type":"FeatureCollection","features":[]}'
    )
    (tmp / "build" / "manifest.json").write_text(json.dumps({
        "shapefile": "data/shapefiles/DRC_Health_zones.shp",
        "n_features": 0,
        "built_at": "2026-05-22T10:00:00+00:00",
        "commit": "newsha1",
        "datasets": [],
    }))
    (tmp / "qa").mkdir()
    (tmp / "qa" / "qa_log.csv").write_text("dataset,type,file,status\nfoo,vector,foo.csv,pass\n")
    (tmp / "qa" / "matrix_log.csv").write_text("dataset,file\n")
    (tmp / "README.md").write_text(README_TEMPLATE)
    (tmp / ".gitignore").write_text("bin/\ngh.log\ndist/\n")


def _init_git(tmp: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp,
        check=True,
    )


def _install_stubs(tmp: Path, *, editor_body: str = "", gh_body: str | None = None) -> tuple[Path, Path]:
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    gh_log = tmp / "gh.log"
    default_gh = (
        f"""#!/usr/bin/env bash
echo "$@" >> {gh_log}
if [ "$1" = "release" ] && [ "$2" = "create" ]; then
  echo "https://github.com/example/repo/releases/tag/$3"
fi
exit 0
"""
    )
    _make_stub(bin_dir / "gh", gh_body or default_gh)
    if editor_body:
        _make_stub(bin_dir / "fake-editor", editor_body)
    return bin_dir, gh_log


def _env(tmp: Path, bin_dir: Path, *, editor: Path | None = None) -> dict:
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "PYTHONPATH": str(REPO_ROOT),
    }
    if editor is not None:
        env["EDITOR"] = str(editor)
    return env


def _run(tmp: Path, env: dict, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tools.release", *extra_args],
        cwd=tmp,
        capture_output=True,
        text=True,
        env=env,
    )


# ---------- preflight ----------

def test_preflight_fails_when_qa_log_missing(tmp_path):
    _seed_repo(tmp_path)
    (tmp_path / "qa" / "qa_log.csv").unlink()
    bin_dir, _ = _install_stubs(tmp_path)
    result = _run(tmp_path, _env(tmp_path, bin_dir))
    assert result.returncode != 0
    assert "qa" in result.stderr.lower()


def test_preflight_fails_when_qa_log_has_failures(tmp_path):
    _seed_repo(tmp_path)
    (tmp_path / "qa" / "qa_log.csv").write_text(
        "dataset,type,file,status\nfoo,vector,foo.csv,fail\n"
    )
    bin_dir, _ = _install_stubs(tmp_path)
    result = _run(tmp_path, _env(tmp_path, bin_dir))
    assert result.returncode != 0
    assert "fail" in result.stderr.lower()


def test_preflight_fails_when_gh_missing(tmp_path):
    _seed_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "tools.release"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"PATH": "/nonexistent-bin", "PYTHONPATH": str(REPO_ROOT), "HOME": str(tmp_path)},
    )
    assert result.returncode != 0
    assert "gh" in result.stderr.lower()


def test_preflight_fails_on_unrelated_dirty_paths(tmp_path):
    _seed_repo(tmp_path)
    _init_git(tmp_path)
    bin_dir, _ = _install_stubs(tmp_path)
    (tmp_path / "unrelated.txt").write_text("dirty")
    result = _run(tmp_path, _env(tmp_path, bin_dir))
    assert result.returncode != 0
    assert "unrelated" in result.stderr.lower() or "dirty" in result.stderr.lower()


# ---------- happy paths ----------

def test_interactive_editor_release(tmp_path):
    """$EDITOR mode (no flags): full pass publishes current build."""
    _seed_repo(tmp_path)
    _init_git(tmp_path)
    editor_body = (
        "#!/usr/bin/env bash\n"
        "cat > \"$1\" <<EOF\n"
        "# stripped comment\n"
        "Updated cross-border POE counts.\n"
        "EOF\n"
    )
    bin_dir, gh_log = _install_stubs(tmp_path, editor_body=editor_body)
    result = _run(tmp_path, _env(tmp_path, bin_dir, editor=bin_dir / "fake-editor"))
    assert result.returncode == 0, result.stderr

    # Archive produced for the CURRENT manifest's tag.
    expected_tag = "build-2026-05-22-newsha1"
    archive = tmp_path / "dist" / f"{expected_tag}.tar.gz"
    assert archive.exists()
    with tarfile.open(archive) as tf:
        names = tf.getnames()
    assert "build/drc_health_zones.geojson" in names
    assert "build/manifest.json" in names
    assert "qa/qa_log.csv" in names

    # gh release create invoked with that tag.
    gh_invocations = gh_log.read_text()
    assert f"release create {expected_tag}" in gh_invocations

    # README updated: past-releases has the new tag at top.
    readme = (tmp_path / "README.md").read_text()
    assert expected_tag in readme
    assert "Updated cross-border POE counts." in readme

    # DESCRIPTION.md NOT written (vestigial in new flow).
    assert not (tmp_path / "build" / "DESCRIPTION.md").exists()


def test_description_file_release(tmp_path):
    """--description-file path: read description from a file, do not open $EDITOR."""
    _seed_repo(tmp_path)
    _init_git(tmp_path)
    bin_dir, gh_log = _install_stubs(tmp_path)
    desc = tmp_path / "desc.md"
    desc.write_text("Refreshed Flowminder month.\n")
    result = _run(
        tmp_path,
        _env(tmp_path, bin_dir),  # no EDITOR set
        "--description-file", str(desc), "--non-interactive",
    )
    assert result.returncode == 0, result.stderr
    readme = (tmp_path / "README.md").read_text()
    assert "Refreshed Flowminder month." in readme
    assert "build-2026-05-22-newsha1" in readme


def test_non_interactive_without_description_file_fails(tmp_path):
    _seed_repo(tmp_path)
    _init_git(tmp_path)
    bin_dir, _ = _install_stubs(tmp_path)
    result = _run(tmp_path, _env(tmp_path, bin_dir), "--non-interactive")
    assert result.returncode != 0
    assert "description-file" in result.stderr.lower() or "non-interactive" in result.stderr.lower()


def test_description_file_empty_fails(tmp_path):
    _seed_repo(tmp_path)
    _init_git(tmp_path)
    bin_dir, _ = _install_stubs(tmp_path)
    desc = tmp_path / "desc.md"
    desc.write_text("   \n\n")
    result = _run(
        tmp_path,
        _env(tmp_path, bin_dir),
        "--description-file", str(desc), "--non-interactive",
    )
    assert result.returncode != 0
    assert "empty" in result.stderr.lower() or "description" in result.stderr.lower()
```

- [ ] **Step 2: Verify the rewritten tests fail (the orchestrator still does the old thing)**

Run: `.venv/bin/python -m pytest tests/test_release_orchestrator.py -v`
Expected: tests fail — likely with assertions about the archive contents (the current orchestrator archives the *previous* build, not the current one) and about `DESCRIPTION.md` existence, plus argparse errors for unknown `--description-file` / `--non-interactive` flags.

- [ ] **Step 3: Rewrite `tools/release.py`**

Replace the file with the new orchestrator. Key changes from the current file: delete `_archive_previous_build`, delete `DESCRIPTION = BUILD_DIR / "DESCRIPTION.md"`, delete the trailing `_bg.main()` call, add CLI flags, and add `_publish_current_build()`.

```python
"""`python -m tools.release` — package the current build/ as a GitHub Release
and update README.

In the new flow:
- The release workflow runs `tools.build_geojson` immediately before invoking
  this script, so `build/` already reflects the data on `main`.
- This script does NOT rebuild and does NOT archive a "previous" build — it
  publishes whatever is currently in build/ as a new release.
- Use `--description-file <path>` to provide the release notes non-interactively
  (CI mode). Otherwise the script opens $EDITOR.

Pure helpers live in tools.lib.release.

Run from repo root:
    python -m tools.release                              # interactive ($EDITOR)
    python -m tools.release --description-file desc.md --non-interactive
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.lib.release import (
    build_tag,
    format_last_build_line,
    pack_archive,
    render_editor_template,
    rewrite_readme,
    strip_editor_comments,
)


REPO_ROOT = Path.cwd()
QA_LOG = REPO_ROOT / "qa" / "qa_log.csv"
MATRIX_LOG = REPO_ROOT / "qa" / "matrix_log.csv"
BUILD_DIR = REPO_ROOT / "build"
MANIFEST = BUILD_DIR / "manifest.json"
README = REPO_ROOT / "README.md"
DIST_DIR = REPO_ROOT / "dist"

ALLOWLIST_PREFIXES = (
    "build/",
    "qa/qa_log.csv",
    "qa/matrix_log.csv",
    "qa/reports/",
    "README.md",
    "dist/",
)


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _preflight() -> int:
    if not QA_LOG.exists():
        _eprint(f"qa log not found at {QA_LOG}; run `python -m tools.qa` first.")
        return 2
    with QA_LOG.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "fail":
                _eprint(
                    "qa log contains failures — resolve them and re-run "
                    "`python -m tools.qa` before releasing."
                )
                return 2
    if shutil.which("gh") is None:
        _eprint("gh CLI not found. Install from https://cli.github.com/ and run `gh auth login`.")
        return 2
    dirty = _git_dirty_paths()
    unrelated = [p for p in dirty if not any(p.startswith(pre) for pre in ALLOWLIST_PREFIXES)]
    if unrelated:
        _eprint(
            "working tree has unrelated uncommitted changes; commit or stash them first:\n"
            + "\n".join(f"  {p}" for p in unrelated)
        )
        return 2
    return 0


def _git_dirty_paths() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    paths: list[str] = []
    for line in result.stdout.splitlines():
        path = line[3:].split(" -> ", 1)[-1].strip()
        if path:
            paths.append(path)
    return paths


def _resolve_description(args: argparse.Namespace) -> str:
    if args.description_file:
        body = Path(args.description_file).read_text(encoding="utf-8").strip()
        if not body:
            _eprint(
                f"description file {args.description_file} is empty after trimming; aborting."
            )
            sys.exit(2)
        return body
    if args.non_interactive:
        _eprint("--non-interactive requires --description-file; aborting.")
        sys.exit(2)
    editor = os.environ.get("EDITOR", "vi")
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f:
            f.write(render_editor_template())
            tmp_path = Path(f.name)
        subprocess.run([editor, str(tmp_path)], check=True)
        raw = tmp_path.read_text()
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
    body = strip_editor_comments(raw)
    if not body:
        _eprint("description is required (empty after stripping comments); aborting.")
        sys.exit(2)
    return body


def _publish_current_build(description: str) -> tuple[str, str]:
    """Pack build/ and create a GitHub Release. Returns (tag, release_url)."""
    manifest = json.loads(MANIFEST.read_text())
    tag = build_tag(manifest["built_at"], manifest["commit"])

    out_path = DIST_DIR / f"{tag}.tar.gz"
    members: list[tuple[Path, str]] = [
        (BUILD_DIR / "drc_health_zones.geojson", "build/drc_health_zones.geojson"),
        (BUILD_DIR / "long", "build/long"),
        (BUILD_DIR / "manifest.json", "build/manifest.json"),
        (QA_LOG, "qa/qa_log.csv"),
        (MATRIX_LOG, "qa/matrix_log.csv"),
    ]
    pack_archive(members, out_path)

    notes_file: Path
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(description)
        notes_file = Path(f.name)
    try:
        create = subprocess.run(
            [
                "gh", "release", "create", tag,
                str(out_path),
                "--title", tag,
                "--notes-file", str(notes_file),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
    finally:
        notes_file.unlink(missing_ok=True)
    if create.returncode != 0:
        _eprint(f"`gh release create` failed:\n{create.stderr}")
        sys.exit(2)
    url_lines = [ln for ln in create.stdout.strip().splitlines() if ln.strip()]
    url = url_lines[-1] if url_lines else ""
    _eprint(f"✓ Published {tag} → {url}")
    return tag, url


def _update_readme(tag: str, url: str, description: str) -> None:
    manifest = json.loads(MANIFEST.read_text())
    built_at = manifest["built_at"]
    short_sha = manifest["commit"]
    current_date = built_at.split("T", 1)[0]

    try:
        head_full = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        head_full = ""

    last_build_line = format_last_build_line(
        built_at=built_at,
        commit_short=short_sha,
        head_full_sha=head_full,
    )
    release_date = tag.split("-", 1)[1].rsplit("-", 1)[0]
    summary_line = description.strip().splitlines()[0]
    past_release_row = (
        f"| [`{tag}`]({url}) | {release_date} | {summary_line} | [release]({url}) |"
    )

    readme = README.read_text()
    readme = rewrite_readme(
        readme,
        last_build_line=last_build_line,
        current_build_date=current_date,
        whats_new=description,
        past_release_row=past_release_row,
    )
    README.write_text(readme, encoding="utf-8")
    _eprint("✓ Updated README.md")


def main() -> int:
    parser = argparse.ArgumentParser(prog="tools.release")
    parser.add_argument(
        "--description-file",
        type=str,
        default=None,
        help="Path to a file containing the release description (skips $EDITOR).",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of prompting. Requires --description-file.",
    )
    args = parser.parse_args()

    rc = _preflight()
    if rc != 0:
        return rc

    description = _resolve_description(args)
    tag, url = _publish_current_build(description)
    _update_readme(tag, url, description)

    _eprint("")
    _eprint("Next: review the changes, then")
    _eprint("  git add build/ qa/qa_log.csv qa/matrix_log.csv qa/reports/ README.md")
    _eprint("  git commit -m \"New build YYYY-MM-DD\"")
    _eprint("  git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Verify orchestrator tests pass**

Run: `.venv/bin/python -m pytest tests/test_release_orchestrator.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS. If any tests outside the release/orchestrator files relied on `build/DESCRIPTION.md`, fix them by removing those expectations (search the tree first: `grep -rn DESCRIPTION.md tests/`).

- [ ] **Step 6: Commit**

```bash
git add tools/release.py tests/test_release_orchestrator.py
git commit -m "Rework tools.release: publish current build, drop archive-previous and trailing rebuild"
```

---

## Task 3: PR template

**Files:**
- Create: `.github/pull_request_template.md`

- [ ] **Step 1: Create the template**

Write `.github/pull_request_template.md`:

```markdown
## What's new

<!-- This section becomes the GitHub Release description and the README "what's new" block. -->
<!-- Write 1–3 sentences describing what changed in this PR from a data/consumer perspective. -->
<!-- The first line is used as the short summary in the README "Past releases" table. -->



## Contributor checklist

- [ ] My PR touches only `data/**`, `tests/**`, and unrelated docs.
- [ ] I did NOT commit changes under `build/`, `qa/`, `dist/`, or to the `README.md` "current build" / "past releases" sections.
- [ ] `pytest` and `python -m tools.qa` pass locally.
- [ ] `data/<dataset>/metadata.yaml` is up to date (`retrieved_on`, source URL, license, contact).
```

- [ ] **Step 2: Commit**

```bash
git add .github/pull_request_template.md
git commit -m "Add PR template requiring '## What's new' section and contributor checklist"
```

---

## Task 4: Release workflow

**Files:**
- Create: `.github/workflows/release.yml`

This is the workflow that runs on `push` to `main` when `data/**` changes and produces a GitHub Release.

- [ ] **Step 1: Create the workflow file**

Write `.github/workflows/release.yml`:

```yaml
name: Release on data merge

on:
  push:
    branches: [main]
    paths:
      - 'data/**'
  workflow_dispatch:
    inputs:
      description:
        description: 'Short release description (one or more lines). Required for manual runs.'
        required: true
        type: string

permissions:
  contents: write

concurrency:
  group: release-main
  cancel-in-progress: false

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Check [skip release] marker
        id: skip
        run: |
          msg=$(git log -1 --pretty=%B "${{ github.sha }}" 2>/dev/null || echo "")
          if echo "$msg" | grep -qF "[skip release]"; then
            echo "skip=true" >> "$GITHUB_OUTPUT"
            echo "Commit message contains [skip release]; exiting."
          else
            echo "skip=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Checkout
        if: steps.skip.outputs.skip != 'true'
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          lfs: true
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Python
        if: steps.skip.outputs.skip != 'true'
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
          cache-dependency-path: tools/requirements.txt

      - name: Install Python dependencies
        if: steps.skip.outputs.skip != 'true'
        run: pip install -r tools/requirements.txt

      - name: Resolve release description
        if: steps.skip.outputs.skip != 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            printf '%s\n' "${{ github.event.inputs.description }}" > /tmp/desc.md
          else
            # Find the PR that introduced this commit.
            gh api "repos/${{ github.repository }}/commits/${{ github.sha }}/pulls" \
              -H "Accept: application/vnd.github+json" > /tmp/pulls.json
            python -c '
import json, sys
from tools.lib.release import extract_whats_new
pulls = json.load(open("/tmp/pulls.json"))
if not pulls:
    print("No PR associated with commit ${{ github.sha }}", file=sys.stderr); sys.exit(2)
body = pulls[0].get("body") or ""
print(extract_whats_new(body))
' > /tmp/desc.md
          fi
          echo "---- description ----"
          cat /tmp/desc.md
          echo "---------------------"

      - name: Run QA
        if: steps.skip.outputs.skip != 'true'
        run: python -m tools.qa

      - name: Build GeoJSON
        if: steps.skip.outputs.skip != 'true'
        run: python -m tools.build_geojson

      - name: Publish release
        if: steps.skip.outputs.skip != 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python -m tools.release \
            --description-file /tmp/desc.md \
            --non-interactive

      - name: Commit build artifacts back to main
        if: steps.skip.outputs.skip != 'true'
        run: |
          set -euo pipefail
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          # Stage only allowlisted release outputs — never anything else.
          git add build/ qa/qa_log.csv qa/matrix_log.csv qa/reports/ README.md
          if git diff --cached --quiet; then
            echo "Nothing to commit."
            exit 0
          fi
          tag=$(python -c "
import json
m = json.load(open('build/manifest.json'))
date = m['built_at'].split('T',1)[0]
print(f\"build-{date}-{m['commit']}\")
")
          git commit -m "CI: release ${tag} [skip release][skip ci]"
          git push origin HEAD:main
```

Notes for the implementer:
- The `if: steps.skip.outputs.skip != 'true'` guard on every subsequent step is verbose but explicit. Do NOT use `continue-on-error` or job-level `if` here — we want individual step-level control so logs clearly show the skip.
- `PYTHONPATH` is implicitly the repo root because `python -m tools.qa` is invoked from the checked-out repo root; no need to set it.
- `secrets.GITHUB_TOKEN` is automatically provided; no PAT needed.

- [ ] **Step 2: Lint the workflow YAML locally**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"`
Expected: no output (parses cleanly).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "Add CI workflow that publishes a release on data/** merges to main"
```

---

## Task 5: README rewrite

**Files:**
- Modify: `README.md`

Restructure the existing single `# Contributor flow` section into three sections: `# Contributor flow` (ends at "open PR"), `# Admin flow` (review + merge + escape hatches), and `# Release internals` (what the CI workflow does).

- [ ] **Step 1: Read the current README and identify the section to replace**

The relevant block to replace is the existing `# Contributor flow` section. Everything from the `# Contributor flow` heading down to the next top-level heading (`# Citation`) should be replaced with the new three sections below. Leave the surrounding sections (`Last successful build:` line, `# Data sources`, `# Current build (YYYY-MM-DD)`, `# Repository layout`, `# Data contract`, `# Citation`, `# License and warranty`) unchanged.

- [ ] **Step 2: Replace the `# Contributor flow` section**

Use `Edit` to swap the old `# Contributor flow` section for these three sections:

````markdown
# Contributor flow

Contributors add or update data. PRs touch `data/**` (and `tests/**` and unrelated docs only) — never `build/`, `qa/`, `dist/`, or `README.md`'s build/release sections.

0.  One-time setup (anyone cloning):

    ```
    git lfs install
    python -m venv .venv && .venv/bin/pip install -r tools/requirements.txt
    ```

    LFS is required because binary raw blobs (`*.xlsx`, `*.zip`, `*.pdf`, `*.tif`, etc.) under `data/*/raw/` are stored via Git LFS — see `.gitattributes`.

1.  Create `data/<your_dataset>/` with `raw/`, `metadata.yaml`, and (when you have outputs) `process.{py,R}` + `processed/`.

2.  Make sure your processed filenames match the contract above. Add any name aliases your data uses to `data/aliases.csv`.

3.  Sync with main:

    ```
    git merge origin/main
    ```

4.  Run unit tests + QA locally:

    ```
    .venv/bin/python -m pytest tests/
    .venv/bin/python -m tools.qa
    ```

5.  *(Optional)* Rebuild the merged GeoJSON locally to sanity-check your changes:

    ```
    .venv/bin/python -m tools.build_geojson --skip-readme
    ```

    **Do not commit the resulting `build/`, `qa/qa_log.csv`, `qa/matrix_log.csv`, `qa/reports/`, or `README.md` updates.** Those land on `main` automatically when an admin merges your PR; including them in your PR causes merge conflicts and gets flagged in review.

6.  Open a PR. **Fill in the `## What's new` section** in the PR body (template provided) — that text becomes the GitHub Release description and the README "what's new" block when this PR is released. CI runs `pytest` + `tools.qa` and blocks merge on any failures.

7.  Wait for admin review and merge. You don't run a release — CI does that automatically.

# Admin flow

Admins (maintainers with write access to `main`) review PRs and merge.

1.  Review the PR: data diff, CI green, `## What's new` section populated and accurate, contributor checklist ticked.

2.  Merge to `main`. **That's it for the common case** — the release workflow takes over.

Escape hatches:

-   **Suppress release for a trivial change** (e.g. typo fix in a metadata file): include `[skip release]` in the merge commit message. CI will skip the release step.
-   **Force a release without a data change** (e.g. after fixing `tools/build_geojson.py`): go to the Actions tab → "Release on data merge" → "Run workflow", and supply a description via the manual input.
-   **Emergency local release** (CI is down): pull `main`, ensure `build/` is current (`python -m tools.build_geojson`), then run `python -m tools.release` interactively. Commit + push `build/`, `qa/`, `README.md` manually.

Maintainers who will cut emergency local releases also need:

-   `gh` CLI installed and authenticated (`gh auth login`).
-   `$EDITOR` set (used by `tools.release` for the interactive description prompt).

# Release internals

The release workflow (`.github/workflows/release.yml`) runs on `push` to `main` when `data/**` changes (and on manual `workflow_dispatch`).

What it does, in order:

1.  Bails if the HEAD commit message contains `[skip release]`.
2.  Extracts the `## What's new` section from the merge commit's PR body (via `gh api`).
3.  Runs `python -m tools.qa`.
4.  Runs `python -m tools.build_geojson`.
5.  Runs `python -m tools.release --description-file <tmp> --non-interactive`, which packs `build/` as a `dist/<tag>.tar.gz` archive, publishes a GitHub Release tagged `build-YYYY-MM-DD-<sha>`, and updates the README.
6.  Commits and pushes the resulting `build/`, `qa/`, and `README.md` back to `main` with `[skip release][skip ci]` in the commit message to prevent recursive triggering.

The pre-existing `qa.yml` workflow runs `pytest` + `tools.qa` on PRs as the merge gate; it does not trigger on `build/`, `qa/`, or `README.md` changes, so the release workflow's commit-back does not retrigger it.

````

- [ ] **Step 3: Verify markdown renders**

Run: `.venv/bin/python -c "import pathlib; print(pathlib.Path('README.md').read_text()[:200])"`
Expected: the top of the README still shows the title and `Last successful build:` line. Then visually inspect by opening the README and confirming the three new sections appear in order and the surrounding content is intact.

- [ ] **Step 4: Re-run the test suite** (the README-rewrite helpers in `tools/lib/release.py` parse the README; make sure the marker comments still exist)

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS.

- [ ] **Step 5: Smoke test a local release end-to-end** (interactive path only — does NOT push)

This validates the rewritten orchestrator against the rewritten README in one go. Skip the `gh release create` by using a dry-run-equivalent: set `PATH` to include only a stub `gh` that succeeds without contacting GitHub. (Alternatively: just rely on the orchestrator integration tests — they cover this. This step is optional manual verification.)

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "Restructure README into Contributor flow / Admin flow / Release internals"
```

---

## Task 6: Final integration sweep

**Files:**
- (read-only) all touched files

- [ ] **Step 1: Confirm clean working tree**

Run: `git status`
Expected: working tree clean.

- [ ] **Step 2: Full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS.

- [ ] **Step 3: Confirm no orphan references to `DESCRIPTION.md` remain**

Run: `grep -rn "DESCRIPTION.md" tools/ tests/ .github/ docs/`
Expected: no hits in `tools/` or `tests/`. A reference in `docs/superpowers/specs/` (mentioning that it's been dropped) is fine.

- [ ] **Step 4: Confirm no orphan references to `_archive_previous_build` remain**

Run: `grep -rn "_archive_previous_build\|archive_previous_build" tools/ tests/`
Expected: no hits.

- [ ] **Step 5: Verify the existing `qa.yml` does NOT trigger on `build/`, `qa/`, or `README.md`-only changes**

Read `.github/workflows/qa.yml`. Confirm `paths:` includes only `data/**`, `tools/**`, `tests/**`, and the workflow file itself — not `build/**`, `qa/**`, `README.md`, or `dist/**`. If `qa.yml` were to fire on the release workflow's commit-back, we would not get an infinite loop (the commit lacks `data/**` changes so even if `qa.yml` did fire, `release.yml` would not), but `[skip ci]` in the commit message is the belt-and-braces safety.

Expected: paths correctly exclude bot-commit targets. No change needed.

- [ ] **Step 6: Branch-protection reminder**

Open an issue or note for the repo admin: configure GitHub branch protection on `main`:

- Require PR before merge.
- Require at least one approving review from a maintainer.
- Require `qa.yml` status check to pass.
- Allow the workflow's `GITHUB_TOKEN` identity to push (default behavior; no extra config needed).

This is repo configuration, not code, and is documented in the spec as recommended but not required.

- [ ] **Step 7: Final commit (if anything fell out of the sweep)**

```bash
# Only commit if changes appeared during the sweep
git status
git commit -m "Final sweep: clean up stragglers from admin-contributor flow rework" || true
```

---

## Self-review notes

Coverage check vs the spec:

- Role split (spec §1) → Task 5 (README) + Task 3 (PR template).
- Repository layout additions (spec §2) → Tasks 3, 4.
- PR template (spec §3) → Task 3.
- Release workflow (spec §4) including `[skip release]`, `workflow_dispatch`, `paths: ['data/**']`, PR-body extraction, `concurrency`, `contents: write` → Task 4.
- `tools.release` rework (spec §5): `--description-file`, `--non-interactive`, drop archive-previous, drop trailing rebuild, drop `DESCRIPTION.md` → Task 2.
- README rewrite (spec §6) → Task 5.
- Branch protection (spec §7) → Task 6 step 6 (documentation reminder; not code).

No placeholders. Type/name consistency:
- `extract_whats_new` used in Task 1 (definition) and Task 4 (workflow `python -c`).
- `--description-file` and `--non-interactive` flags consistent in Task 2 (definition) and Task 4 (workflow invocation).
- `[skip release]` marker consistent in Task 4 (workflow check) and Task 4 (commit-back message) and Task 5 (README docs).

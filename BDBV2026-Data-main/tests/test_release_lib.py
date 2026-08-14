"""Unit tests for pure helpers in tools.lib.release."""

import tarfile

import pytest

from tools.lib.release import (
    build_tag,
    format_human_timestamp,
    format_last_build_line,
    pack_archive,
    render_editor_template,
    replace_last_build_line,
    rewrite_readme,
    strip_editor_comments,
)


# ---------- README build stamp helpers ----------


def test_format_human_timestamp_utc():
    assert format_human_timestamp("2026-05-22T18:27:39+00:00") == (
        "22 May 2026, 18:27:39 (UTC)"
    )


def test_format_last_build_line_includes_timestamp_and_links():
    line = format_last_build_line(
        built_at="2026-05-22T18:27:39+00:00",
        commit_short="493d506",
        head_full_sha="3e1e714ad800d0002cb3a5d2e1c926a61105e61a",
        github_repo="kraemer-lab/Ebola_DRC_2026",
    )
    assert line.startswith("Last successful build: **22 May 2026, 18:27:39 (UTC)**")
    assert "[`3e1e714`](https://github.com/kraemer-lab/Ebola_DRC_2026/commit/3e1e714ad800d0002cb3a5d2e1c926a61105e61a)" in line
    assert "[`493d506`](https://github.com/kraemer-lab/Ebola_DRC_2026/commit/493d506)" in line


def test_replace_last_build_line_swaps_single_line():
    readme = "Header\n\nLast successful build: **OLD** (commit `x`).\n\n# Current build (2026-01-01)\n"
    new_line = format_last_build_line(
        built_at="2026-05-22T18:27:39+00:00",
        commit_short="abc1234",
    )
    out = replace_last_build_line(readme, new_line)
    assert "Last successful build: **OLD**" not in out
    assert new_line in out


# ---------- build_tag ----------

def test_build_tag_combines_date_and_sha():
    assert build_tag("2026-05-21", "396cf8a") == "build-2026-05-21-396cf8a"


def test_build_tag_accepts_iso_timestamp_and_truncates_to_date():
    assert build_tag("2026-05-21T14:30:00+00:00", "abc1234") == "build-2026-05-21-abc1234"


def test_build_tag_rejects_empty_sha():
    with pytest.raises(ValueError, match="sha"):
        build_tag("2026-05-21", "")


def test_build_tag_rejects_empty_date():
    with pytest.raises(ValueError, match="date"):
        build_tag("", "abc1234")


# ---------- editor helpers ----------

def test_render_editor_template_starts_with_comment_lines():
    tpl = render_editor_template()
    lines = tpl.splitlines()
    assert all(line.startswith("#") or line == "" for line in lines[:4])
    assert "what's new" in tpl.lower()
    assert "first line" in tpl.lower()


def test_strip_editor_comments_drops_hash_prefixed_lines():
    raw = (
        "# Lines starting with '#' are ignored.\n"
        "# Describe what's new.\n"
        "\n"
        "Refreshed ACLED extract; added new flowminder month.\n"
        "\n"
        "Motivated by the WHO sitrep update.\n"
    )
    out = strip_editor_comments(raw)
    assert out == (
        "Refreshed ACLED extract; added new flowminder month.\n"
        "\n"
        "Motivated by the WHO sitrep update."
    )


def test_strip_editor_comments_returns_empty_when_only_comments():
    raw = "# comment one\n# comment two\n"
    assert strip_editor_comments(raw) == ""


def test_strip_editor_comments_preserves_inline_hashes():
    """A '#' that isn't the first non-whitespace char of a line is content."""
    raw = "Updated dataset #42 with new metrics.\n"
    assert strip_editor_comments(raw) == "Updated dataset #42 with new metrics."


# ---------- pack_archive ----------

def test_pack_archive_writes_tarball_with_expected_arcnames(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.txt").write_text("alpha")
    nested = src_dir / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("bravo")

    members = [
        (src_dir / "a.txt", "build/a.txt"),
        (src_dir / "nested", "build/nested"),
    ]
    out = tmp_path / "out.tar.gz"

    pack_archive(members, out)

    assert out.exists()
    with tarfile.open(out, "r:gz") as tf:
        names = sorted(tf.getnames())
    assert "build/a.txt" in names
    assert "build/nested/b.txt" in names


def test_pack_archive_raises_on_missing_source(tmp_path):
    out = tmp_path / "out.tar.gz"
    with pytest.raises(FileNotFoundError):
        pack_archive([(tmp_path / "does-not-exist", "x")], out)


# ---------- rewrite_readme ----------

SAMPLE_README = """\
# Header

Last successful build: **OLD TIMESTAMP** (commit `oldsha1`).

# Current build (2026-01-01)

Some prose.

<!-- whats-new:start -->
old description
<!-- whats-new:end -->

More prose.

## Past releases

<!-- past-releases:start -->
| Tag | Date | Summary | Download |
|-----|------|---------|----------|
| build-2026-01-01-oldsha1 | 2026-01-01 | initial | [release](https://example/old) |
<!-- past-releases:end -->

# Repository layout
"""


def test_rewrite_readme_updates_last_build_line():
    out = rewrite_readme(
        SAMPLE_README,
        last_build_line="Last successful build: **21 May 2026** (commit `newsha1`).",
        current_build_date="2026-05-21",
        whats_new="Brand new content.",
        past_release_row="| build-2026-05-21-newsha1 | 2026-05-21 | did stuff | [release](https://example/new) |",
    )
    assert "**21 May 2026**" in out
    assert "commit `newsha1`" in out
    assert "OLD TIMESTAMP" not in out


def test_rewrite_readme_updates_current_build_heading():
    out = rewrite_readme(
        SAMPLE_README,
        last_build_line="Last successful build: **X** (commit `a`).",
        current_build_date="2026-05-21",
        whats_new="x",
        past_release_row="| t | d | s | [r](u) |",
    )
    assert "# Current build (2026-05-21)" in out
    assert "# Current build (2026-01-01)" not in out


def test_rewrite_readme_replaces_whats_new_block():
    out = rewrite_readme(
        SAMPLE_README,
        last_build_line="Last successful build: **X** (commit `a`).",
        current_build_date="2026-05-21",
        whats_new="Refreshed ACLED. Added new month of Flowminder.",
        past_release_row="| t | d | s | [r](u) |",
    )
    assert "Refreshed ACLED" in out
    assert "old description" not in out
    assert "<!-- whats-new:start -->" in out
    assert "<!-- whats-new:end -->" in out


def test_rewrite_readme_prepends_past_release_row():
    out = rewrite_readme(
        SAMPLE_README,
        last_build_line="Last successful build: **X** (commit `a`).",
        current_build_date="2026-05-21",
        whats_new="x",
        past_release_row="| build-2026-05-21-newsha1 | 2026-05-21 | new entry | [release](https://example/new) |",
    )
    new_idx = out.index("build-2026-05-21-newsha1")
    old_idx = out.index("build-2026-01-01-oldsha1")
    assert new_idx < old_idx
    assert out.count("|-----|------|---------|----------|") == 1


def test_rewrite_readme_is_idempotent_outside_markers():
    out1 = rewrite_readme(
        SAMPLE_README,
        last_build_line="Last successful build: **X** (commit `a`).",
        current_build_date="2026-05-21",
        whats_new="x",
        past_release_row="| t | d | s | [r](u) |",
    )
    assert "Some prose." in out1
    assert "More prose." in out1
    assert "# Repository layout" in out1


def test_rewrite_readme_handles_empty_past_release_row():
    """Empty past_release_row preserves existing rows; no stray blank inserted."""
    out = rewrite_readme(
        SAMPLE_README,
        last_build_line="Last successful build: **X** (commit `a`).",
        current_build_date="2026-05-21",
        whats_new="x",
        past_release_row="",
    )
    # Old row should still be present
    assert "build-2026-01-01-oldsha1" in out
    # Header still there
    assert "|-----|------|---------|----------|" in out


def test_rewrite_readme_raises_on_missing_marker():
    broken = SAMPLE_README.replace("<!-- whats-new:end -->", "")
    with pytest.raises(ValueError, match="whats-new:end"):
        rewrite_readme(
            broken,
            last_build_line="Last successful build: **X** (commit `a`).",
            current_build_date="2026-05-21",
            whats_new="x",
            past_release_row="| t | d | s | [r](u) |",
        )

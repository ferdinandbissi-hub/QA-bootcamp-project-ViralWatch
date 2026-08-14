"""README stamping after tools.build_geojson."""

import re

import pytest

from tools import build_geojson
from tools.lib.release import format_last_build_line, replace_last_build_line


def test_stamp_readme_updates_line(tmp_path, monkeypatch):
    """_stamp_readme rewrites the Last successful build line from manifest fields."""
    readme = tmp_path / "README.md"
    readme.write_text(
        "Title\n\n"
        "Last successful build: **OLD** — stale.\n\n"
        "# Current build (2020-01-01)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(build_geojson, "README", readme)
    monkeypatch.setattr(
        build_geojson,
        "_git_head_shas",
        lambda: ("3e1e714ad800d0002cb3a5d2e1c926a61105e61a", "3e1e714"),
    )

    build_geojson._stamp_readme({
        "built_at": "2026-05-22T18:27:39+00:00",
        "commit": "493d506",
    })

    body = readme.read_text(encoding="utf-8")
    assert "Last successful build: **OLD**" not in body
    assert re.search(
        r"Last successful build: \*\*22 May 2026, 18:27:39 \(UTC\)\*\*",
        body,
    )
    assert "# Current build (2026-05-22)" in body


def test_replace_last_build_line_raises_when_missing():
    with pytest.raises(ValueError, match="Last successful build"):
        replace_last_build_line("no build line here\n", format_last_build_line(
            built_at="2026-05-22T18:27:39+00:00",
            commit_short="abc1234",
        ))

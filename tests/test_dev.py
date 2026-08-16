from __future__ import annotations

from pathlib import Path

from scripts.dev import data_snapshot


def test_data_snapshot_tracks_only_mortgage_data_files(tmp_path: Path) -> None:
    (tmp_path / "loans").mkdir()
    loan = tmp_path / "loans/example.yaml"
    loan.write_text("id: example\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored\n", encoding="utf-8")

    before = data_snapshot(tmp_path)
    assert [item[0] for item in before] == ["loans/example.yaml"]

    loan.write_text("id: updated-example\n", encoding="utf-8")
    after = data_snapshot(tmp_path)
    assert after != before

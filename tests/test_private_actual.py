from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

from mortgage.data import DATA_DIR_ENV, validate_data_directory
from mortgage.report import build_forecast


ROOT = Path(__file__).parent.parent
PRIVATE_DATA_DIR = os.environ.get(DATA_DIR_ENV)


@pytest.mark.private_actual
@pytest.mark.skipif(
    not PRIVATE_DATA_DIR,
    reason="private actual tests: skipped (MORTGAGE_DATA_DIR is not set)",
)
def test_external_actual_schedules_match_exactly() -> None:
    data_dir = Path(PRIVATE_DATA_DIR or "")
    validate_data_directory(data_dir)
    document = build_forecast(
        ROOT,
        generated_at=datetime.fromisoformat("2026-08-15T12:00:00+09:00"),
        data_dir=data_dir,
        data_source_type="external",
    )

    assert document["data_source"] == {"type": "external"}
    assert document["actual"]["monthly_results"]
    assert document["model_status"]["golden_tests_passed"] is True
    assert document["model_status"]["maximum_balance_error_yen"] == 0
    assert all(
        loan["actual_validation"]["maximum_balance_error_yen"] == 0
        for loan in document["loans"]
    )

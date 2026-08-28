from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

import mortgage.data as data_module
import mortgage.report as report_module
from mortgage.data import DataValidationError, resolve_data_directory, validate_data_directory


ROOT = Path(__file__).parent.parent
SAMPLE_DATA = ROOT / "sample-data"


def copied_sample(tmp_path: Path) -> Path:
    destination = tmp_path / "data"
    shutil.copytree(SAMPLE_DATA, destination)
    return destination


def test_data_directory_priority_is_cli_then_environment_then_sample(tmp_path: Path) -> None:
    external = copied_sample(tmp_path)

    by_cli = resolve_data_directory(
        ROOT,
        external,
        {"MORTGAGE_DATA_DIR": str(tmp_path / "unused")},
    )
    by_environment = resolve_data_directory(
        ROOT, environment={"MORTGAGE_DATA_DIR": str(external)}
    )
    by_default = resolve_data_directory(ROOT, environment={})
    explicit_sample = resolve_data_directory(ROOT, SAMPLE_DATA, environment={})

    assert by_cli.path == external.resolve()
    assert by_cli.source_type == "external"
    assert by_environment.path == external.resolve()
    assert by_default.path == SAMPLE_DATA.resolve()
    assert by_default.source_type == "sample"
    assert explicit_sample.path == SAMPLE_DATA.resolve()
    assert explicit_sample.source_type == "sample"


def test_missing_required_file_has_clear_error(tmp_path: Path) -> None:
    data_dir = copied_sample(tmp_path)
    (data_dir / "sources.yaml").unlink()

    with pytest.raises(DataValidationError, match="sources.yaml"):
        validate_data_directory(data_dir)


def test_malformed_yaml_has_clear_error(tmp_path: Path) -> None:
    data_dir = copied_sample(tmp_path)
    (data_dir / "sources.yaml").write_text("sources: [", encoding="utf-8")

    with pytest.raises(DataValidationError, match="Malformed YAML"):
        validate_data_directory(data_dir)


def test_dashboard_chart_setting_must_be_boolean(tmp_path: Path) -> None:
    data_dir = copied_sample(tmp_path)
    manifest = data_dir / "data-schema.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "show_trend_charts: true", 'show_trend_charts: "false"'
        ),
        encoding="utf-8",
    )

    with pytest.raises(DataValidationError, match="show_trend_charts must be a boolean"):
        validate_data_directory(data_dir)


def test_assumed_payment_setting_must_be_boolean(tmp_path: Path) -> None:
    data_dir = copied_sample(tmp_path)
    manifest = data_dir / "data-schema.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "assume_scheduled_payments: false",
            'assume_scheduled_payments: "true"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        DataValidationError,
        match="assume_scheduled_payments must be a boolean",
    ):
        validate_data_directory(data_dir)


def test_borrower_birth_year_must_not_be_after_current_balance_year(
    tmp_path: Path,
) -> None:
    data_dir = copied_sample(tmp_path)
    loan = data_dir / "loans/example-loan.yaml"
    loan.write_text(
        loan.read_text(encoding="utf-8").replace(
            "borrower_birth_year: 1980", "borrower_birth_year: 2027"
        ),
        encoding="utf-8",
    )

    with pytest.raises(DataValidationError, match="borrower_birth_year"):
        validate_data_directory(data_dir)


def test_invalid_and_duplicated_loan_ids_are_rejected(tmp_path: Path) -> None:
    invalid = copied_sample(tmp_path / "invalid")
    loan_path = invalid / "loans/example-loan.yaml"
    loan_path.write_text(
        loan_path.read_text(encoding="utf-8").replace(
            "id: example-loan", "id: Example Loan"
        ),
        encoding="utf-8",
    )
    with pytest.raises(DataValidationError, match="Invalid loan id"):
        validate_data_directory(invalid)

    duplicated = copied_sample(tmp_path / "duplicated")
    shutil.copy(
        duplicated / "loans/example-loan.yaml",
        duplicated / "loans/another-loan.yaml",
    )
    with pytest.raises(DataValidationError, match="Duplicated loan id"):
        validate_data_directory(duplicated)


def test_actual_csv_required_fields_are_validated(tmp_path: Path) -> None:
    data_dir = copied_sample(tmp_path)
    actual = data_dir / "actual/example-loan.csv"
    actual.write_text("date,payment\n2026-09-20,65000\n", encoding="utf-8")

    with pytest.raises(DataValidationError, match="missing fields"):
        validate_data_directory(data_dir)


def test_actual_csv_is_required_for_each_loan(tmp_path: Path) -> None:
    data_dir = copied_sample(tmp_path)
    (data_dir / "actual/example-loan.csv").unlink()

    with pytest.raises(DataValidationError, match="missing actual CSV for: example-loan"):
        validate_data_directory(data_dir)


@pytest.mark.parametrize(
    ("relative_path", "target_path"),
    [
        ("sources.yaml", "sample-data/sources.yaml"),
        ("loans/example-loan.yaml", "sample-data/loans/example-loan.yaml"),
        ("actual/example-loan.csv", "sample-data/actual/example-loan.csv"),
    ],
)
def test_symbolic_links_inside_data_root_are_rejected(
    tmp_path: Path, relative_path: str, target_path: str
) -> None:
    data_dir = copied_sample(tmp_path)
    linked_path = data_dir / relative_path
    linked_path.unlink()
    linked_path.symlink_to(ROOT / target_path)

    with pytest.raises(DataValidationError, match="Symbolic links are not allowed"):
        validate_data_directory(data_dir)


def test_yaml_size_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = copied_sample(tmp_path)
    monkeypatch.setattr(data_module, "MAX_YAML_BYTES", 8)

    with pytest.raises(DataValidationError, match="data file exceeds"):
        validate_data_directory(data_dir)


def test_actual_row_limit_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = copied_sample(tmp_path)
    monkeypatch.setattr(data_module, "MAX_ACTUAL_ROWS", 1)

    with pytest.raises(DataValidationError, match="row limit"):
        validate_data_directory(data_dir)


def test_scenario_count_limit_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = copied_sample(tmp_path)
    monkeypatch.setattr(data_module, "MAX_SCENARIOS", 1)

    with pytest.raises(DataValidationError, match="Scenario count"):
        validate_data_directory(data_dir)


def test_estimated_simulation_work_limit_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = copied_sample(tmp_path)
    monkeypatch.setattr(data_module, "MAX_SIMULATION_MONTHS", 1)

    with pytest.raises(DataValidationError, match="simulation workload"):
        validate_data_directory(data_dir)


@pytest.mark.parametrize("unsafe_rate", ["NaN", "1E+999999"])
def test_non_finite_or_extreme_rates_are_rejected(
    tmp_path: Path, unsafe_rate: str
) -> None:
    data_dir = copied_sample(tmp_path)
    scenarios = data_dir / "rates/scenarios.yaml"
    scenarios.write_text(
        scenarios.read_text(encoding="utf-8").replace(
            '    - "0.010"', f'    - "{unsafe_rate}"', 1
        ),
        encoding="utf-8",
    )

    with pytest.raises(DataValidationError, match="must be finite"):
        validate_data_directory(data_dir)


def test_file_swapped_for_symlink_after_validation_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = copied_sample(tmp_path)
    loan_path = data_dir / "loans/example-loan.yaml"
    outside = tmp_path / "outside-loan.yaml"
    shutil.copy(loan_path, outside)
    original_validate = data_module.validate_data_directory

    def validate_then_swap(selected: Path) -> None:
        original_validate(selected)
        loan_path.unlink()
        loan_path.symlink_to(outside)

    monkeypatch.setattr(
        report_module, "validate_data_directory", validate_then_swap
    )

    with pytest.raises(DataValidationError, match="safely read"):
        report_module.build_forecast(
            ROOT,
            generated_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
            data_dir=data_dir,
        )

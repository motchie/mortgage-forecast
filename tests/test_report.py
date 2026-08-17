from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from mortgage.report import _combined_balance_series, build_forecast
from mortgage.scenarios import (
    build_payment_dates,
    load_loan_forecast_input,
    load_scenario_config,
    resolve_scenario_rates,
)


ROOT = Path(__file__).parent.parent
SAMPLE_DATA = ROOT / "sample-data"
GENERATED_AT = datetime.fromisoformat("2026-08-15T12:00:00+09:00")


def test_combined_balance_series_carries_each_loan_forward() -> None:
    results = (
        SimpleNamespace(
            starting_balance=100,
            monthly_results=(
                SimpleNamespace(date=date(2026, 1, 11), balance_after=90),
                SimpleNamespace(date=date(2026, 3, 11), balance_after=70),
            ),
        ),
        SimpleNamespace(
            starting_balance=200,
            monthly_results=(
                SimpleNamespace(date=date(2026, 2, 20), balance_after=180),
                SimpleNamespace(date=date(2026, 3, 20), balance_after=160),
            ),
        ),
    )

    assert _combined_balance_series(results) == [
        {"month": "2026-01", "balance": 290},
        {"month": "2026-02", "balance": 270},
        {"month": "2026-03", "balance": 230},
    ]


def build_document() -> dict[str, Any]:
    return build_forecast(ROOT, generated_at=GENERATED_AT)


def projection(document: dict[str, Any]) -> dict[str, Any]:
    selected_rates = {0.018, 0.03, 0.04, 0.05}
    cases = {
        str(case["annual_rate"]): {
            "maximum_monthly_payment": case["maximum_monthly_payment"],
            "cap_triggers": case["payment_cap_trigger_count"],
            "unpaid_first_date": case["first_unpaid_interest_date"],
            "final_payment": case["final_payment"],
            "extra_final_payment": case["extra_final_payment"],
        }
        for case in document["sensitivity"][0]["cases"]
        if case["annual_rate"] in selected_rates
    }
    scenario_summaries = []
    for scenario in document["scenarios"]:
        if scenario["id"] not in {"current", "base", "higher", "stress"}:
            continue
        result = scenario["results"][0]
        scenario_summaries.append(
            {
                "id": scenario["id"],
                "maximum_monthly_payment": result["maximum_monthly_payment"],
                "cap_triggers": result["payment_cap_trigger_count"],
                "unpaid_first_date": result["unpaid_interest"]["first_date"],
                "final_payment": result["final_payment"],
                "extra_final_payment": result["extra_final_payment"],
            }
        )
    return {
        "schema_version": document["schema_version"],
        "data_source": document["data_source"],
        "presentation": document["presentation"],
        "generated_at": document["generated_at"],
        "model_status": document["model_status"],
        "actual_row_count": len(document["actual"]["monthly_results"]),
        "loan_ids": [loan["id"] for loan in document["loans"]],
        "scenario_summaries": scenario_summaries,
        "sensitivity": cases,
        "warning_codes": sorted({w["code"] for w in document["warnings"]}),
    }


def test_public_document_matches_json_schema() -> None:
    schema = json.loads((ROOT / "schemas/forecast.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    assert list(validator.iter_errors(build_document())) == []


def test_public_document_includes_borrower_birth_year() -> None:
    assert build_document()["loans"][0]["borrower_birth_year"] == 1980


def test_scheduled_payments_can_advance_current_state_as_an_inference(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    shutil.copytree(SAMPLE_DATA, data_dir)
    manifest = data_dir / "data-schema.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "assume_scheduled_payments: false",
            "assume_scheduled_payments: true",
        ),
        encoding="utf-8",
    )

    document = build_forecast(
        ROOT,
        data_dir=data_dir,
        generated_at=datetime.fromisoformat("2026-09-21T03:15:00+09:00"),
    )
    current = document["loans"][0]["current"]

    assert current == {
        "balance": 13_956_000,
        "balance_date": "2026-09-20",
        "basis_balance_date": "2026-08-20",
        "annual_rate": 0.018,
        "monthly_payment": 65_000,
        "assumed_payment_count": 1,
        "verification_status": "inferred",
    }
    assert document["combined"]["current_balance"] == 13_956_000
    assert document["scenarios"][0]["results"][0]["starting_date"] == "2026-09-20"


def test_public_document_snapshot() -> None:
    expected = json.loads(
        (ROOT / "tests/fixtures/forecast_snapshot.json").read_text()
    )
    assert projection(build_document()) == expected


def test_public_document_contains_no_private_keys_or_local_paths() -> None:
    document = build_document()
    serialized = json.dumps(document, ensure_ascii=False).lower()
    forbidden_keys = {
        "customer_name",
        "address",
        "account_number",
        "branch_number",
        "transaction_number",
        "pdf_filename",
        "source_path",
        "local_path",
    }

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value).union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    assert forbidden_keys.isdisjoint(keys(document))
    assert "/home/" not in serialized
    assert "/mnt/" not in serialized
    assert "c:\\" not in serialized
    assert ".pdf" not in serialized


def test_artificial_six_percent_case_keeps_unverified_review_warning() -> None:
    document = build_document()
    case = next(
        case
        for case in document["sensitivity"][0]["cases"]
        if case["annual_rate"] == 0.06
    )

    assert case["first_unpaid_interest_date"] == "2026-09-20"
    assert case["unpaid_interest_resolved_date"] == "2031-11-20"
    assert any(
        warning["code"] == "UNVERIFIED_UNPAID_INTEREST_REVIEW"
        and warning["verification_status"] == "unverified"
        for warning in case["warnings"]
    )


def test_artificial_sample_and_combined_outputs_are_present() -> None:
    document = build_document()

    assert document["data_source"] == {"type": "sample"}
    assert [loan["id"] for loan in document["loans"]] == ["example-loan"]
    assert document["combined"]["current_balance"] == 14_000_000
    assert document["combined"]["current_monthly_payment"] == 65_000
    for scenario in document["scenarios"]:
        if scenario["id"] in {"current", "base", "higher", "stress"}:
            assert [result["loan_id"] for result in scenario["results"]] == [
                "example-loan"
            ]
    assert {item["loan_id"] for item in document["sensitivity"]} == {
        "example-loan"
    }
    assert len(document["combined"]["sensitivity"]) == 10


def test_current_scenario_uses_sample_loans_own_rate() -> None:
    document = build_document()
    current = next(
        scenario for scenario in document["scenarios"] if scenario["id"] == "current"
    )
    config = load_scenario_config(SAMPLE_DATA / "rates/scenarios.yaml")
    definition = next(
        scenario for scenario in config.scenarios if scenario.metadata.id == "current"
    )
    loan = load_loan_forecast_input(SAMPLE_DATA / "loans/example-loan.yaml")

    assert current["rate_source"] == "loan_current"
    assert resolve_scenario_rates(
        definition, loan, build_payment_dates(loan)
    ).annual_rates[0] == Decimal("0.0180")


def test_generator_is_deterministic_for_fixed_timestamp(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    command = [
        sys.executable,
        str(ROOT / "scripts/generate_forecast.py"),
        "--generated-at",
        GENERATED_AT.isoformat(),
    ]

    subprocess.run(command + ["--output", str(first)], check=True)
    subprocess.run(command + ["--output", str(second)], check=True)

    assert first.read_bytes() == second.read_bytes()

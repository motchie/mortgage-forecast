"""Resolve and validate sample or external mortgage data directories."""

from __future__ import annotations

import csv
import io
import os
import re
import stat
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

import yaml


DATA_DIR_ENV = "MORTGAGE_DATA_DIR"
DATA_SCHEMA_VERSION = "1.0"
LOAN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ACTUAL_FIELDS = {"date", "payment", "principal", "interest", "balance_after"}
MAX_YAML_BYTES = 1_048_576
MAX_CSV_BYTES = 5_242_880
MAX_LOANS = 50
MAX_ACTUAL_ROWS = 12_000
MAX_SOURCES = 500
MAX_SCENARIOS = 50
MAX_SENSITIVITY_RATES = 200
MAX_RATE_POINTS = 1_000
MAX_FORECAST_DAYS = 36_600
MAX_SIMULATION_MONTHS = 500_000
MAX_PAYMENT_REVIEW_DATES = 1_000
MAX_MONEY_YEN = 1_000_000_000_000_000
MAX_ABSOLUTE_RATE = Decimal("10")


class DataValidationError(ValueError):
    """Raised when a selected data directory is incomplete or malformed."""


@dataclass(frozen=True, slots=True)
class ResolvedDataDirectory:
    path: Path
    source_type: str


def read_data_text(data_dir: Path, path: Path, *, maximum_bytes: int) -> str:
    """Read one confined regular file from the descriptor that was verified."""

    data_dir = data_dir.resolve()
    try:
        relative = path.relative_to(data_dir).as_posix()
    except ValueError as error:
        raise DataValidationError(f"Mortgage data path escapes its root: {path}") from error

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise DataValidationError(
                f"Mortgage data path must be a regular file: {relative}"
            )
        resolved = path.resolve(strict=True)
        named = os.stat(path, follow_symlinks=False)
        if not resolved.is_relative_to(data_dir) or not stat.S_ISREG(named.st_mode):
            raise DataValidationError(f"Mortgage data path escapes its root: {relative}")
        if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
            raise DataValidationError(
                f"Mortgage data path changed while it was being opened: {relative}"
            )
        with os.fdopen(descriptor, "rb") as file:
            descriptor = -1
            contents = file.read(maximum_bytes + 1)
        if len(contents) > maximum_bytes:
            raise DataValidationError(
                f"Mortgage data file exceeds {maximum_bytes} bytes: {relative}"
            )
        return contents.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DataValidationError(
            f"Mortgage data file is not valid UTF-8: {relative}"
        ) from error
    except DataValidationError:
        raise
    except OSError as error:
        raise DataValidationError(f"Cannot safely read mortgage data: {relative}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _load_mapping(data_dir: Path, path: Path) -> dict[str, object]:
    try:
        value = yaml.safe_load(
            read_data_text(data_dir, path, maximum_bytes=MAX_YAML_BYTES)
        )
    except yaml.YAMLError as error:
        raise DataValidationError(f"Malformed YAML in {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise DataValidationError(f"{path.name} must contain a YAML mapping")
    return value


def _require_safe_child(data_dir: Path, path: Path, *, directory: bool) -> None:
    """Require a regular, non-link child contained by the selected data root."""

    relative = path.relative_to(data_dir).as_posix()
    if path.is_symlink():
        raise DataValidationError(
            f"Symbolic links are not allowed in mortgage data: {relative}"
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise DataValidationError(
            f"Mortgage data path is missing or unreadable: {relative}"
        ) from error
    if not resolved.is_relative_to(data_dir):
        raise DataValidationError(f"Mortgage data path escapes its root: {relative}")
    valid_type = resolved.is_dir() if directory else resolved.is_file()
    if not valid_type:
        expected = "directory" if directory else "regular file"
        raise DataValidationError(
            f"Mortgage data path must be a {expected}: {relative}"
        )


def _as_date(value: object, *, field: str, filename: str) -> date:
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError as error:
        raise DataValidationError(f"Invalid {field} in {filename}: {value!r}") from error


def _require_sequence_limit(value: object, maximum: int, label: str) -> None:
    if not isinstance(value, (list, tuple)):
        raise DataValidationError(f"{label} must be a list")
    if len(value) > maximum:
        raise DataValidationError(f"{label} exceeds the limit of {maximum}")


def _bounded_integer(value: object, *, label: str, minimum: int = 0) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as error:
        raise DataValidationError(f"{label} must be an integer") from error
    if not minimum <= parsed <= MAX_MONEY_YEN:
        raise DataValidationError(
            f"{label} must be between {minimum} and {MAX_MONEY_YEN}"
        )
    return parsed


def _bounded_rate(
    value: object, *, label: str, allow_negative: bool = False
) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise DataValidationError(f"{label} must be a decimal rate") from error
    lower = -MAX_ABSOLUTE_RATE if allow_negative else Decimal(0)
    if not parsed.is_finite() or not lower <= parsed <= MAX_ABSOLUTE_RATE:
        raise DataValidationError(
            f"{label} must be finite and between {lower} and {MAX_ABSOLUTE_RATE}"
        )
    return parsed


def resolve_data_directory(
    repository_root: Path,
    cli_data_dir: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> ResolvedDataDirectory:
    """Resolve CLI, environment, then repository sample data in that order."""

    environment = os.environ if environment is None else environment
    if cli_data_dir is not None:
        selected = cli_data_dir
        source_type = "external"
    elif environment.get(DATA_DIR_ENV):
        selected = Path(environment[DATA_DIR_ENV])
        source_type = "external"
    else:
        selected = repository_root / "sample-data"
        source_type = "sample"
    path = selected.expanduser().resolve()
    validate_data_directory(path)
    return ResolvedDataDirectory(path=path, source_type=source_type)


def validate_data_directory(data_dir: Path) -> None:
    """Validate structure and identifiers without silently falling back."""

    if not data_dir.is_dir():
        raise DataValidationError(
            f"Mortgage data directory does not exist: {data_dir}"
        )
    data_dir = data_dir.resolve()
    required = (
        (data_dir / "data-schema.yaml", False),
        (data_dir / "loans", True),
        (data_dir / "actual", True),
        (data_dir / "rates", True),
        (data_dir / "rates/actual-rates.yaml", False),
        (data_dir / "rates/scenarios.yaml", False),
        (data_dir / "sources.yaml", False),
    )
    missing = [
        path.relative_to(data_dir).as_posix()
        for path, _ in required
        if not path.exists()
    ]
    if missing:
        raise DataValidationError(
            f"Mortgage data directory is missing: {', '.join(missing)}"
        )
    for path, directory in required:
        _require_safe_child(data_dir, path, directory=directory)

    manifest = _load_mapping(data_dir, data_dir / "data-schema.yaml")
    version = str(manifest.get("data_schema_version", ""))
    if version != DATA_SCHEMA_VERSION:
        raise DataValidationError(
            f"Unsupported data_schema_version {version!r}; expected {DATA_SCHEMA_VERSION!r}"
        )

    loan_paths = sorted((data_dir / "loans").glob("*.yaml"))
    if not loan_paths:
        raise DataValidationError("Mortgage data directory has no loan YAML files")
    if len(loan_paths) > MAX_LOANS:
        raise DataValidationError(f"Loan count exceeds the limit of {MAX_LOANS}")
    loan_entries: list[tuple[Path, str]] = []
    forecast_months = 0
    for path in loan_paths:
        _require_safe_child(data_dir, path, directory=False)
        raw = _load_mapping(data_dir, path)
        loan_id = str(raw.get("id", ""))
        if not LOAN_ID_PATTERN.fullmatch(loan_id):
            raise DataValidationError(f"Invalid loan id in {path.name}: {loan_id!r}")
        current = raw.get("current")
        repayment = raw.get("repayment")
        interest_calculation = raw.get("interest_calculation")
        rate = raw.get("rate")
        if not all(
            isinstance(section, dict)
            for section in (current, repayment, interest_calculation, rate)
        ):
            raise DataValidationError(
                f"Loan sections in {path.name} must be YAML mappings"
            )
        rate_model = rate.get("rate_model")
        payment_review = repayment.get("payment_review")
        if not isinstance(rate_model, dict) or not isinstance(payment_review, dict):
            raise DataValidationError(
                f"Rate and payment review settings in {path.name} must be mappings"
            )
        schedule = payment_review.get("schedule")
        if not isinstance(schedule, dict):
            raise DataValidationError(
                f"Payment review schedule in {path.name} must be a mapping"
            )
        _require_sequence_limit(
            schedule.get("dates"),
            MAX_PAYMENT_REVIEW_DATES,
            f"payment review dates in {path.name}",
        )
        _bounded_integer(
            raw.get("original_principal"),
            label=f"original_principal in {path.name}",
            minimum=1,
        )
        _bounded_integer(
            current.get("balance"), label=f"current.balance in {path.name}"
        )
        _bounded_integer(
            current.get("monthly_payment"),
            label=f"current.monthly_payment in {path.name}",
        )
        _bounded_integer(
            interest_calculation.get("balance_unit_yen"),
            label=f"interest_calculation.balance_unit_yen in {path.name}",
            minimum=1,
        )
        _bounded_rate(
            current.get("annual_rate"),
            label=f"current.annual_rate in {path.name}",
        )
        _bounded_rate(
            rate_model.get("spread"),
            label=f"rate_model.spread in {path.name}",
            allow_negative=True,
        )
        current_date = _as_date(
            current.get("balance_date"),
            field="current.balance_date",
            filename=path.name,
        )
        maturity_date = _as_date(
            raw.get("maturity_date"), field="maturity_date", filename=path.name
        )
        forecast_days = (maturity_date - current_date).days
        if not 0 <= forecast_days <= MAX_FORECAST_DAYS:
            raise DataValidationError(
                f"Forecast horizon in {path.name} must be between 0 and "
                f"{MAX_FORECAST_DAYS} days"
            )
        forecast_months += forecast_days // 28 + 1
        loan_entries.append((path, loan_id))
    loan_ids = [loan_id for _, loan_id in loan_entries]
    duplicates = sorted(
        {loan_id for loan_id in loan_ids if loan_ids.count(loan_id) > 1}
    )
    if duplicates:
        raise DataValidationError(f"Duplicated loan id: {', '.join(duplicates)}")
    for path, loan_id in loan_entries:
        if path.stem != loan_id:
            raise DataValidationError(
                f"Loan filename {path.name!r} must match id {loan_id!r}"
            )

    rates = _load_mapping(data_dir, data_dir / "rates/actual-rates.yaml")
    scenarios = _load_mapping(data_dir, data_dir / "rates/scenarios.yaml")
    sources = _load_mapping(data_dir, data_dir / "sources.yaml")
    if not isinstance(sources.get("sources"), list):
        raise DataValidationError("sources.yaml must contain a sources list")
    if len(sources["sources"]) > MAX_SOURCES:
        raise DataValidationError(f"Source count exceeds the limit of {MAX_SOURCES}")
    raw_scenarios = scenarios.get("scenarios")
    if not isinstance(raw_scenarios, dict):
        raise DataValidationError("scenarios.yaml must contain a scenarios mapping")
    if len(raw_scenarios) > MAX_SCENARIOS:
        raise DataValidationError(
            f"Scenario count exceeds the limit of {MAX_SCENARIOS}"
        )
    settings = scenarios.get("settings")
    if not isinstance(settings, dict):
        raise DataValidationError("scenarios.yaml must contain a settings mapping")
    _require_sequence_limit(
        settings.get("sensitivity_rates"),
        MAX_SENSITIVITY_RATES,
        "settings.sensitivity_rates",
    )
    for index, value in enumerate(settings["sensitivity_rates"]):
        _bounded_rate(value, label=f"settings.sensitivity_rates[{index}]")
    estimated_simulation_months = forecast_months * (
        len(raw_scenarios) + len(settings["sensitivity_rates"])
    )
    if estimated_simulation_months > MAX_SIMULATION_MONTHS:
        raise DataValidationError(
            "Estimated simulation workload exceeds the limit of "
            f"{MAX_SIMULATION_MONTHS} loan-scenario months"
        )
    for scenario_id, scenario in raw_scenarios.items():
        if not isinstance(scenario, dict):
            raise DataValidationError(f"Scenario {scenario_id!r} must be a mapping")
        annual_rate = scenario.get("annual_rate")
        if annual_rate is not None and annual_rate != "current":
            _bounded_rate(
                annual_rate, label=f"scenario {scenario_id!r}.annual_rate"
            )
        if scenario.get("terminal_rate") is not None:
            _bounded_rate(
                scenario["terminal_rate"],
                label=f"scenario {scenario_id!r}.terminal_rate",
            )
        for field in ("rates", "short_prime"):
            if field in scenario:
                _require_sequence_limit(
                    scenario[field],
                    MAX_RATE_POINTS,
                    f"scenario {scenario_id!r}.{field}",
                )
                for index, point in enumerate(scenario[field]):
                    if not isinstance(point, dict):
                        raise DataValidationError(
                            f"scenario {scenario_id!r}.{field}[{index}] "
                            "must be a mapping"
                        )
                    _bounded_rate(
                        point.get("annual_rate"),
                        label=(
                            f"scenario {scenario_id!r}.{field}[{index}].annual_rate"
                        ),
                    )
    for loan_id, rate_config in rates.items():
        if not isinstance(rate_config, dict):
            raise DataValidationError(f"Rate config for {loan_id!r} must be a mapping")
        _require_sequence_limit(
            rate_config.get("changes"),
            MAX_RATE_POINTS,
            f"rate changes for {loan_id!r}",
        )
        for index, change in enumerate(rate_config["changes"]):
            if not isinstance(change, dict):
                raise DataValidationError(
                    f"rate changes for {loan_id!r}[{index}] must be a mapping"
                )
            _bounded_rate(
                change.get("annual_rate"),
                label=f"rate changes for {loan_id!r}[{index}].annual_rate",
            )

    actual_dir = data_dir / "actual"
    missing_actual = [
        loan_id
        for loan_id in loan_ids
        if not (actual_dir / f"{loan_id}.csv").is_file()
    ]
    if missing_actual:
        raise DataValidationError(
            f"Mortgage data directory is missing actual CSV for: {', '.join(missing_actual)}"
        )
    for path in sorted(actual_dir.glob("*.csv")):
        _require_safe_child(data_dir, path, directory=False)
        if path.stem not in loan_ids:
            raise DataValidationError(
                f"Actual CSV {path.name!r} has no matching loan configuration"
            )
        contents = read_data_text(data_dir, path, maximum_bytes=MAX_CSV_BYTES)
        reader = csv.DictReader(io.StringIO(contents, newline=""))
        fields = set(reader.fieldnames or ())
        missing_fields = sorted(ACTUAL_FIELDS - fields)
        if missing_fields:
            raise DataValidationError(
                f"Actual CSV {path.name!r} is missing fields: {', '.join(missing_fields)}"
            )
        for row_count, row in enumerate(reader, start=1):
            if row_count > MAX_ACTUAL_ROWS:
                raise DataValidationError(
                    f"Actual CSV {path.name!r} exceeds the row limit of "
                    f"{MAX_ACTUAL_ROWS}"
                )
            for field in ACTUAL_FIELDS - {"date"}:
                _bounded_integer(
                    row.get(field),
                    label=f"{field} in {path.name} row {row_count}",
                )
        if path.stem not in rates:
            raise DataValidationError(
                f"actual-rates.yaml has no entry for {path.stem!r}"
            )

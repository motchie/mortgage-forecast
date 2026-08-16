#!/usr/bin/env python3
"""Generate forecast JSON from sample data or an external private data directory."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mortgage.report import build_forecast, default_generated_at  # noqa: E402
from mortgage.data import DataValidationError, resolve_data_directory  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Mortgage data directory; overrides MORTGAGE_DATA_DIR and sample data.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dashboard/public/generated/forecast.json",
    )
    parser.add_argument(
        "--generated-at",
        type=datetime.fromisoformat,
        help="Fixed ISO-8601 timestamp for deterministic builds and tests.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generated_at = args.generated_at or default_generated_at()
    try:
        resolved = resolve_data_directory(ROOT, args.data_dir)
        document = build_forecast(
            ROOT,
            generated_at=generated_at,
            data_dir=resolved.path,
            data_source_type=resolved.source_type,
        )
    except DataValidationError as error:
        raise SystemExit(f"Invalid mortgage data: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {args.output}")


if __name__ == "__main__":
    main()

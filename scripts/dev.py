#!/usr/bin/env python3
"""Generate forecast data and run the local dashboard with data auto-refresh."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_SUFFIXES = {".csv", ".yaml", ".yml"}

sys.path.insert(0, str(ROOT))

from mortgage.data import DataValidationError, resolve_data_directory  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate forecast.json and start the local dashboard."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Mortgage data directory; overrides MORTGAGE_DATA_DIR and sample data.",
    )
    parser.add_argument(
        "--no-watch",
        action="store_true",
        help="Do not regenerate forecast.json when data files change.",
    )
    return parser.parse_args()


def data_snapshot(data_dir: Path) -> tuple[tuple[str, int, int], ...]:
    """Return a stable snapshot of relevant file names, mtimes, and sizes."""

    return tuple(
        sorted(
            (
                path.relative_to(data_dir).as_posix(),
                path.stat().st_mtime_ns,
                path.stat().st_size,
            )
            for path in data_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in DATA_SUFFIXES
        )
    )


def generate_forecast(data_dir: Path | None) -> bool:
    command = [sys.executable, str(ROOT / "scripts/generate_forecast.py")]
    if data_dir is not None:
        command.extend(("--data-dir", str(data_dir)))
    return subprocess.run(command, cwd=ROOT, check=False).returncode == 0


def npm_executable() -> str:
    candidates = ("npm.cmd", "npm") if os.name == "nt" else ("npm",)
    executable = next(
        (found for name in candidates if (found := shutil.which(name))), None
    )
    if executable is None:
        raise SystemExit("npm が見つかりません。Node.jsをinstallしてください。")
    return executable


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> None:
    args = parse_args()
    try:
        resolved = resolve_data_directory(ROOT, args.data_dir)
    except DataValidationError as error:
        raise SystemExit(f"Invalid mortgage data: {error}") from error

    if not generate_forecast(args.data_dir):
        raise SystemExit("forecast.jsonの生成に失敗しました。")

    source_label = "sample" if resolved.source_type == "sample" else "external"
    print(f"Dashboard data: {source_label}")
    if not args.no_watch:
        print("Data auto-refresh: enabled")

    process = subprocess.Popen(
        [npm_executable(), "run", "dev"],
        cwd=ROOT / "dashboard",
    )
    snapshot = data_snapshot(resolved.path)
    stopped_by_user = False
    try:
        while process.poll() is None:
            time.sleep(1)
            if args.no_watch:
                continue
            try:
                current = data_snapshot(resolved.path)
            except OSError:
                continue
            if current == snapshot:
                continue
            snapshot = current
            print("Mortgage data changed; regenerating forecast.json...")
            if not generate_forecast(args.data_dir):
                print("Regeneration failed; keeping the previous forecast.json.")
    except KeyboardInterrupt:
        stopped_by_user = True
        print("\nStopping dashboard...")
    finally:
        stop_process(process)

    if not stopped_by_user and process.returncode != 0:
        raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()

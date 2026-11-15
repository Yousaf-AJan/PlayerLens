"""Explicit local processing commands; no network access or model loading."""

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

from playerlens import __version__
from playerlens.validation import DatasetValidationError, validate_csv, write_issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate local Steam review data.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Check the full input; write local summary and issues.")
    validate.add_argument("--input", type=Path, default=Path("data/raw/elden_ring_steam_reviews.csv"))
    validate.add_argument("--output", type=Path, default=Path("artifacts/validation"))
    args = parser.parse_args(argv)
    started = datetime.now(timezone.utc).isoformat()
    try:
        source = args.input.resolve()
        output = args.output.resolve()
        if output == source.parent or source.parent in output.parents:
            raise DatasetValidationError("Output must be outside the input directory to protect source data.")
        result = validate_csv(source)
        output.mkdir(parents=True, exist_ok=True)
        (output / "summary.json").write_text(
            json.dumps(result.summary, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        write_issues(output / "issues.csv", result.issues)
        manifest = {
            "started_at_utc": started,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_path": str(source), "output_path": str(output),
            "input_sha256": result.summary["input"]["sha256"],
            "settings": result.summary["settings"],
            "python": platform.python_version(), "platform": platform.platform(),
            "dependencies": {name: version(name) for name in ("playerlens", "pandas", "numpy")},
            "outputs": ["summary.json", "issues.csv"],
            "status": result.summary["validation"]["status"],
        }
        (output / "run.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, DatasetValidationError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 2
    text = result.summary["text"]
    checks = result.summary["validation"]
    print(f"Rows: {result.summary['rows']:,}; nonblank reviews: {text['nonblank']:,}; blank: {text['blank']:,}")
    print(f"Status: {checks['status']}; errors: {checks['error_count']}; warnings: {checks['warning_count']}")
    print(f"SHA-256: {result.summary['input']['sha256']}")
    print(f"Reports: {output}")
    return 1 if checks["error_count"] else 0

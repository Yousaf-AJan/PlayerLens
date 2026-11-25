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
    parser = argparse.ArgumentParser(description="Validate and explore local Steam review data.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Check the full input; write local summary and issues.")
    validate.add_argument("--input", type=Path, default=Path("data/raw/elden_ring_steam_reviews.csv"))
    validate.add_argument("--output", type=Path, default=Path("artifacts/validation"))
    eda = commands.add_parser("eda", help="Write descriptive tables, figures and a local EDA report.")
    eda.add_argument("--input", type=Path, default=Path("data/raw/elden_ring_steam_reviews.csv"))
    eda.add_argument("--output", type=Path, default=Path("artifacts/eda"))
    prepare = commands.add_parser('prepare', help='Prepare source-linked passages and a grouped annotation sample.')
    prepare.add_argument('--input',type=Path,default=Path('data/raw/elden_ring_steam_reviews.csv'))
    prepare.add_argument('--output',type=Path,default=Path('data/processed/m3-ready'))
    prepare.add_argument('--exclusions',type=Path,default=Path('data/annotations/development_exclusions.json'))
    annotate = commands.add_parser('annotate',help='Open the local pilot-only annotation form.')
    annotate.add_argument('--prepared',type=Path,default=Path('data/processed/m3-ready'))
    annotate.add_argument('--annotations',type=Path,default=Path('data/annotations/m3'))
    annotate.add_argument('--split',choices=['development','test'],default='development')
    annotate.add_argument('--mode',choices=['assisted','manual','reference'],default='assisted')
    annotate.add_argument('--proposals',type=Path,default=Path('data/proposals/m3-assisted-v1'))
    annotate.add_argument('--decisions',type=Path,default=Path('data/annotations/m3-assisted-v1'))
    propose = commands.add_parser('propose',help='Write immutable rules-first development proposals, not reference labels.')
    propose.add_argument('--prepared',type=Path,default=Path('data/processed/m3-ready'))
    propose.add_argument('--output',type=Path,default=Path('data/proposals/m3-assisted-v1'))
    propose.add_argument('--cohort',choices=['pilot','development'],default='pilot')
    freeze = commands.add_parser('freeze-annotations',help='Reserved for explicit post-pilot approval; currently locked.')
    args = parser.parse_args(argv)
    if args.command == 'freeze-annotations':
        print('Taxonomy remains provisional. Post-pilot review and explicit freeze approval are required.',file=sys.stderr)
        return 2
    if args.command in ('prepare','annotate','propose'):
        try:
            if args.command == 'propose':
                from playerlens.proposal_store import generate_proposals
                print(json.dumps(generate_proposals(args.prepared,args.output,args.cohort),sort_keys=True))
                return 0
            if args.command == 'prepare':
                from playerlens.preparation_report import prepare_run
                summary = prepare_run(args.input,args.output,args.exclusions)
                print(json.dumps(summary,sort_keys=True))
                return 0
            if args.split == 'test':
                raise ValueError('Held-out annotation is locked until post-pilot approval')
            if args.mode == 'reference':
                raise ValueError('Independent reference annotation is locked until pilot/guideline readiness approval')
            from playerlens.preparation_report import load_prepared
            load_prepared(args.prepared)
            import subprocess
            if args.mode == 'assisted':
                from playerlens.proposal_store import load_proposals
                run,tables = load_prepared(args.prepared)
                load_proposals(args.proposals,run,tables['sampling_manifest'])
                return subprocess.call([sys.executable,'-B','-m','streamlit','run',str(Path(__file__).with_name('assisted_app.py')),
                    '--server.address=127.0.0.1','--server.headless=true','--browser.gatherUsageStats=false','--',
                    '--prepared',str(args.prepared.resolve()),'--proposals',str(args.proposals.resolve()),'--decisions',str(args.decisions.resolve())])
            return subprocess.call([sys.executable,'-B','-m','streamlit','run',str(Path(__file__).with_name('annotation_app.py')),
                '--server.address=127.0.0.1','--server.headless=true','--browser.gatherUsageStats=false','--',
                '--prepared',str(args.prepared.resolve()),'--annotations',str(args.annotations.resolve())])
        except (OSError,ValueError) as exc:
            print(f'{args.command} failed: {exc}',file=sys.stderr)
            return 2
    started = datetime.now(timezone.utc).isoformat()
    try:
        source = args.input.resolve()
        output = args.output.resolve()
        if output == source.parent or source.parent in output.parents:
            raise DatasetValidationError("Output must be outside the input directory to protect source data.")
        if args.command == "eda":
            from time import perf_counter
            from playerlens.eda import build_eda
            from playerlens.eda_report import write_eda_report

            clock = perf_counter()
            try:
                result = validate_csv(source)
                analysis = build_eda(result)
                write_eda_report(analysis, output, source, started)
            except ValueError as exc:
                print(f"EDA failed: {exc}", file=sys.stderr)
                return 2
            print(f"EDA: {analysis.summary['rows']:,} reviews; {analysis.summary['validation']['status']}")
            print(f"Elapsed: {perf_counter() - clock:.3f}s; reports: {output}")
            print("Aspect usefulness is not estimated; development examples are qualitative only.")
            return 1 if result.summary["validation"]["error_count"] else 0
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
        action = "EDA" if args.command == "eda" else "Validation"
        print(f"{action} failed: {exc}", file=sys.stderr)
        return 2
    text = result.summary["text"]
    checks = result.summary["validation"]
    print(f"Rows: {result.summary['rows']:,}; nonblank reviews: {text['nonblank']:,}; blank: {text['blank']:,}")
    print(f"Status: {checks['status']}; errors: {checks['error_count']}; warnings: {checks['warning_count']}")
    print(f"SHA-256: {result.summary['input']['sha256']}")
    print(f"Reports: {output}")
    return 1 if checks["error_count"] else 0

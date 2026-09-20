from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.job_runner import run_diagnostic


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taiko-pack1-builder",
        description="Read-only CIA diagnostics for Taiko Pack1 Builder.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    diagnose = subparsers.add_parser("diagnose", help="inspect a CIA without modifying it")
    diagnose.add_argument("source", type=Path, help="path to the source CIA")
    diagnose.add_argument("--output", type=Path, help="atomic JSON report destination")
    diagnose.add_argument(
        "--profile",
        default="taiko3ds3_jp_pack1",
        help="profile directory name (default: %(default)s)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command != "diagnose":
        return 3
    try:
        report = run_diagnostic(args.source, profile_name=args.profile, output=args.output)
    except (OSError, ValueError) as exc:
        print(f"diagnostic failed: {exc}", file=sys.stderr)
        return 3

    if args.output is None:
        json.dump(report.to_dict(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    if report.status == "PASS":
        return 0
    if report.status == "WARNING":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


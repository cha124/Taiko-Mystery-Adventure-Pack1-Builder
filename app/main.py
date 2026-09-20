from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.core.job_runner import run_diagnostic
from app.core.tja import check_tja_file
from app.core.tja.decoder import TjaDecodeError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taiko-pack1-builder",
        description="Read-only CIA and strict TJA diagnostics for Taiko Pack1 Builder.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    diagnose = subparsers.add_parser("diagnose", help="inspect a CIA without modifying it")
    diagnose.add_argument("source", type=Path, help="path to the source CIA")
    diagnose.add_argument("--output", type=Path, help="atomic JSON report destination")
    diagnose.add_argument(
        "--include-source-path",
        action="store_true",
        help="include the absolute source path in JSON output (off by default)",
    )
    diagnose.add_argument(
        "--profile",
        default="taiko3ds3_jp_pack1",
        help="profile directory name (default: %(default)s)",
    )
    tja_check = subparsers.add_parser("tja-check", help="parse and validate a TJA file")
    tja_check.add_argument("source", type=Path, help="path to the TJA file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "diagnose":
        try:
            report = run_diagnostic(
                args.source,
                profile_name=args.profile,
                output=args.output,
                include_source_path=args.include_source_path,
            )
        except (OSError, ValueError) as exc:
            print(f"diagnostic failed: {exc}", file=sys.stderr)
            return 3
        payload = report.to_dict()
        print(f"CIA DIAGNOSTIC: {report.status}")
        print(f"Title ID: {payload.get('title_id') or '(unavailable)'}")
        print(f"Detected songs: {payload['summary']['detected_song_count']}")
        print(f"Errors: {payload['summary']['error_count']}")
        print(f"Warnings: {payload['summary']['warning_count']}")
        if args.output is not None:
            print(f"Report: {args.output.resolve()}")
        else:
            print("JSON report not written (use --output with an explicit path).")
        if report.status == "PASS":
            return 0
        if report.status == "WARNING":
            return 1
        return 2

    if args.command == "tja-check":
        try:
            report = check_tja_file(args.source)
        except (OSError, TjaDecodeError) as exc:
            print(f"TJA INVALID\n\n{exc}", file=sys.stderr)
            return 3
        valid = report.syntax_valid
        print(f"TJA SYNTAX: {'VALID' if valid else 'INVALID'}")
        print(f"TARGET CONVERSION: {report.conversion_eligibility.value}")
        if report.conversion_blockers:
            print()
            print("Blockers:")
            for blocker in report.conversion_blockers:
                print(f"- {blocker}")
        print()
        print(f"Title: {report.document.header.title or '(missing)'}")
        print(f"BPM: {report.document.header.bpm or '(invalid/missing)'}")
        print("Courses:")
        found = {course.kind.value for course in report.document.courses}
        for name in ("Easy", "Normal", "Hard", "Oni", "Ura"):
            print(f"  {name}: {'yes' if name in found else 'no'}")
        print()
        for message in report.validation.messages:
            prefix = f"{message.location}\n" if message.location else ""
            print(f"{prefix}{message.severity.value}: {message.message}")
        print(f"Errors: {len(report.validation.errors)}")
        print(f"Warnings: {len(report.validation.warnings)}")
        if not valid:
            return 2
        if not report.conversion_eligible or report.validation.warnings:
            return 1
        return 0
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

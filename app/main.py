from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.core.audio.analyzer import run_audio_forensics, run_audio_scan
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
    audio_scan = subparsers.add_parser(
        "audio-scan", help="inspect Pack1 NAAC/ADTS streams without modifying them"
    )
    audio_scan.add_argument("source", type=Path, help="path to the source CIA")
    audio_scan.add_argument("--output", type=Path, help="atomic JSON report destination")
    audio_scan.add_argument(
        "--include-source-path",
        action="store_true",
        help="include the absolute source path in JSON output (off by default)",
    )
    audio_scan.add_argument(
        "--profile",
        default="taiko3ds3_jp_pack1",
        help="profile directory name (default: %(default)s)",
    )
    audio_forensics = subparsers.add_parser(
        "audio-forensics",
        help="compare read-only NAAC header cohorts without modifying the CIA",
    )
    audio_forensics.add_argument("source", type=Path, help="path to the source CIA")
    audio_forensics.add_argument("--output", type=Path, help="atomic JSON report destination")
    audio_forensics.add_argument(
        "--include-source-path",
        action="store_true",
        help="include the absolute source path in JSON output (off by default)",
    )
    audio_forensics.add_argument(
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

    if args.command == "audio-scan":
        try:
            report = run_audio_scan(
                args.source,
                output=args.output,
                include_source_path=args.include_source_path,
                profile_name=args.profile,
            )
        except (OSError, ValueError) as exc:
            print(f"audio scan failed: {exc}", file=sys.stderr)
            return 3
        payload = report.to_dict()
        summary = payload["summary"]
        print(f"AUDIO SCAN: {report.status}")
        print(f"Songs: {summary['song_count']}")
        print(f"Main references: {summary['main_references']}")
        print(f"Preview references: {summary['preview_references']}")
        print(f"Success: {summary['success_count']}")
        print(f"Failures: {summary['failure_count']}")
        print(f"Warnings: {summary['warning_count']}")
        print(f"Errors: {summary['error_count']}")
        if args.output is not None:
            print(f"Report: {args.output.resolve()}")
        else:
            print("JSON report not written (use --output with an explicit path).")
        if report.status == "PASS":
            return 0
        if report.status == "WARNING":
            return 1
        return 2

    if args.command == "audio-forensics":
        try:
            payload = run_audio_forensics(
                args.source,
                output=args.output,
                include_source_path=args.include_source_path,
                profile_name=args.profile,
            )
        except (OSError, ValueError) as exc:
            print(f"audio forensics failed: {exc}", file=sys.stderr)
            return 3
        safety = payload["safety"]
        print(f"AUDIO FORENSICS: {safety['audio_scan_status']}")
        print(f"Decision: {payload['decision']}")
        print(f"Successful NAAC files: {payload['cohorts']['all']['file_count']}")
        print(
            "MPEG1 decoded nominal samples candidate: "
            f"{payload['mpeg_id_1']['decoded_nominal_samples_candidate']['status']}"
        )
        print(
            "MPEG1 payload size candidate: "
            f"{payload['mpeg_id_1']['payload_size_candidate']['status']}"
        )
        if args.output is not None:
            print(f"Report: {args.output.resolve()}")
        else:
            print("JSON report not written (use --output with an explicit path).")
        if safety["audio_scan_status"] == "FAIL":
            return 2
        if payload["decision"] != "READY_FOR_AUDIO_CANDIDATE_PROTOTYPE":
            return 1
        return 0

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

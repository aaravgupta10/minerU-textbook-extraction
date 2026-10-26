#!/usr/bin/env python
"""
Orchestrates 00 -> 06 (-> 07) for a scope, skipping any stage already marked
done in output/<scope>/<year>/_state.json unless --force. This is what you
actually run; the numbered scripts underneath are also runnable standalone
for debugging one stage at a time.

05_validate.py checks structure (right file counts, non-empty, frontmatter).
06_verify_accuracy.py checks whether the extracted CONTENT is actually
correct (independent PyMuPDF cross-check, boundary-leak/latex/caption
heuristics, and a rendered human spot-check package under
output/<scope>/<year>/review/review.md) - read that before trusting a run,
especially the pilot.

Usage:
    python scripts/run_pipeline.py --pilot
    python scripts/run_pipeline.py --year 2026_jan
    python scripts/run_pipeline.py --all                 # every year, in sequence
    python scripts/run_pipeline.py --all --cleanup        # + free disk after each year verifies
"""
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def run(script: str, *args: str):
    argv = [sys.executable, str(SCRIPTS_DIR / script), *args]
    print(f"\n$ {' '.join(argv)}")
    result = subprocess.run(argv)
    if result.returncode != 0:
        print(f"FAILED: {script} {' '.join(args)} (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true")
    g.add_argument("--year")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--cleanup", action="store_true",
                     help="Also run 07_cleanup.py --execute after a year verifies (never for --pilot)")
    ap.add_argument("--skip-labels", action="store_true",
                     help="Skip 00_recover_labels.py (already run and don't want to redo it)")
    ap.add_argument("--no-review", action="store_true",
                     help="Skip rendering the human spot-check page images in 06_verify_accuracy.py")
    args = ap.parse_args()

    scope_flag = ["--pilot"] if args.pilot else (["--all"] if args.all else ["--year", args.year])
    force_flag = ["--force"] if args.force else []

    if not args.skip_labels and not args.pilot:
        run("00_recover_labels.py", *(["--year", args.year] if args.year else []))

    run("02_run_mineru.py", *scope_flag, *force_flag)
    run("03_caption_images_bedrock.py", *scope_flag, *force_flag)
    run("04_split_questions.py", *scope_flag, *force_flag)
    run("05_validate.py", *scope_flag)
    run("06_verify_accuracy.py", *scope_flag, *(["--no-review"] if args.no_review else []))

    if args.cleanup and not args.pilot:
        run("07_cleanup.py", *scope_flag, "--execute")

    print("\nDone. Check output/<scope>/<year>/qa_report.md and accuracy_report.md, "
          "and eyeball output/<scope>/<year>/review/review.md.")


if __name__ == "__main__":
    main()

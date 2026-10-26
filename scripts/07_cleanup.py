#!/usr/bin/env python
"""
Frees disk space on the GPU box after a year's questions_md/ has validated
cleanly: deletes MinerU's bulky per-page debug output (layout preview PDFs,
full-page renders, *_middle.json) while always keeping anything under an
"images" folder (the actual figure crops questions_md/ references) and the
content_list.json (so 04_split_questions.py can still be re-run with
--force later without repeating the GPU-expensive MinerU pass).

Refuses to touch the pilot scope (small on purpose, useful to keep around
for comparison) and refuses a year that hasn't validated cleanly.

Defaults to a DRY RUN - prints what it would delete and the space it would
free, does nothing destructive unless you pass --execute.

Usage:
    python scripts/07_cleanup.py --year 2026_jan            # dry run
    python scripts/07_cleanup.py --year 2026_jan --execute  # actually delete
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import config, scope  # noqa: E402

_DELETE_SUFFIXES = {".png", ".jpg", ".jpeg"}  # only when NOT under an "images" dir
_DELETE_NAME_HINTS = ["_middle.json", "layout", "_model.json", "_origin.pdf", "spans.pdf"]
_KEEP_NAME_HINTS = ["content_list", "mineru.log"]


def _should_delete(path: Path) -> bool:
    if "images" in {p.lower() for p in path.parts}:
        return False
    name = path.name.lower()
    if any(hint in name for hint in _KEEP_NAME_HINTS):
        return False
    if any(hint in name for hint in _DELETE_NAME_HINTS):
        return True
    return path.suffix.lower() in _DELETE_SUFFIXES


def run_one(sy: scope.ScopeYear, execute: bool):
    if sy.scope == config.PILOT_SCOPE:
        print(f"[{sy.scope}/{sy.year_name}] refusing to clean up the pilot scope, it's small on purpose")
        return
    state = scope.load_state(sy)
    if state.get("qa_result") == "FAIL" or not state.get("validated"):
        print(f"[{sy.scope}/{sy.year_name}] SKIP: hasn't structurally validated yet (run 05_validate.py)")
        return
    if state.get("accuracy_result") == "FAIL":
        print(f"[{sy.scope}/{sy.year_name}] SKIP: accuracy verification flagged FAIL "
              f"(run/review 06_verify_accuracy.py before cleaning up)")
        return
    if state.get("cleaned"):
        print(f"[{sy.scope}/{sy.year_name}] already cleaned")
        return
    if not sy.mineru_out_dir.exists():
        return

    to_delete = [p for p in sy.mineru_out_dir.rglob("*") if p.is_file() and _should_delete(p)]
    total = sum(p.stat().st_size for p in to_delete)
    print(f"[{sy.scope}/{sy.year_name}] {len(to_delete)} file(s), {total / 1024 / 1024:.1f} MB "
          f"{'DELETED' if execute else 'would be deleted (dry run)'}")
    if execute:
        for p in to_delete:
            p.unlink()
        scope.save_state(sy, cleaned=True, cleaned_bytes=total)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--year")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--execute", action="store_true", help="Actually delete (default is dry run)")
    args = ap.parse_args()

    years = [y.name for y in config.year_dirs()] if args.all else [args.year]
    for y in years:
        for sy in scope.iter_scope(y):
            run_one(sy, args.execute)


if __name__ == "__main__":
    main()

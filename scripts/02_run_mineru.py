#!/usr/bin/env python
"""
Runs `mineru parse` once per year (or once on the pilot's small subset PDF),
against the local `managed` GPU server. Needs a GPU and an installed
`mineru`, plus (once per machine, not once per run):
    mineru-kit models download --tier standard
    mineru config set parse_server.local.mode managed
    mineru telemetry disable   (avoids an interactive prompt on first run)
- will not run on a laptop.

Usage:
    python scripts/02_run_mineru.py --pilot
    python scripts/02_run_mineru.py --year 2026_jan
    python scripts/02_run_mineru.py --all
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import config, mineru_adapter, scope  # noqa: E402


def run_one(sy: scope.ScopeYear, force: bool):
    state = scope.load_state(sy)
    if state.get("mineru_done") and not force:
        print(f"[{sy.scope}/{sy.year_name}] mineru already done, skipping (--force to redo)")
        return

    sy.ensure_working_pdf()
    log_path = sy.out_dir / "logs" / "mineru.log"
    print(f"[{sy.scope}/{sy.year_name}] running mineru on {sy.working_pdf} -> {sy.mineru_output_md}")
    mineru_adapter.run_mineru(sy.working_pdf, sy.mineru_output_md, log_path)
    scope.save_state(sy, mineru_done=True)
    print(f"[{sy.scope}/{sy.year_name}] done")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true")
    g.add_argument("--year")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true", help="Re-run even if already marked done")
    args = ap.parse_args()

    scopes = [config.PILOT_SCOPE] if args.pilot else (
        [y.name for y in config.year_dirs()] if args.all else [args.year]
    )
    for s in scopes:
        for sy in scope.iter_scope(s):
            run_one(sy, args.force)


if __name__ == "__main__":
    main()

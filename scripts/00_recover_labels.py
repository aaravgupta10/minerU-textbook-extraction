#!/usr/bin/env python
"""
Recover missing shift/date labels for years where Stage 1 left `paper: ""`
(currently: 2026_jan fully, 2026_april partially - see progress.md). Safe to
run on a laptop; no GPU/MinerU/Bedrock involved. Writes
output/<year>/label_overrides.json and is a no-op for years that already
have every section labeled.

Usage:
    python scripts/00_recover_labels.py             # all years
    python scripts/00_recover_labels.py --year 2026_jan
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import config, labels  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", help="Single year folder name, e.g. 2026_jan")
    args = ap.parse_args()

    years = config.year_dirs()
    if args.year:
        years = [y for y in years if y.name == args.year]
        if not years:
            print(f"Unknown year '{args.year}'", file=sys.stderr)
            sys.exit(1)

    for year_dir in years:
        result = labels.recover_labels(year_dir)
        n = len(result["labels"])
        if n == 0 and not result["unmatched"]:
            print(f"{year_dir.name}: all sections already labeled, nothing to do")
            continue
        print(f"{year_dir.name}: recovered {n} section label(s) from removed_ads.pdf")
        for section_idx, label in sorted(result["labels"].items(), key=lambda kv: int(kv[0])):
            print(f"    section {section_idx}: {label}")
        if result["unmatched"]:
            print(f"    WARNING: {len(result['unmatched'])} section(s) still unmatched: "
                  f"{result['unmatched']}")


if __name__ == "__main__":
    main()

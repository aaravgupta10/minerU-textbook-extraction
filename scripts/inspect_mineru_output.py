#!/usr/bin/env python
"""
Calibration tool - run this FIRST on the AWS box, on one small MinerU output
directory (e.g. after running 02_run_mineru.py --pilot for just one year),
before trusting the full pipeline. Prints the actual file tree and, for each
JSON file, its shape (list length, first item's keys) so common/mineru_adapter.py's
candidate filename/field-name lists can be corrected in one line if the
installed MinerU version's output differs from what the adapter guesses.

Usage:
    python scripts/inspect_mineru_output.py output/_pilot/2018/mineru_raw
"""
import json
import sys
from pathlib import Path


def describe_json(path: Path, max_items: int = 1):
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"    (could not parse: {e})")
        return
    if isinstance(data, list):
        print(f"    list of {len(data)} item(s)")
        for item in data[:max_items]:
            if isinstance(item, dict):
                print(f"    first item keys: {sorted(item.keys())}")
                print(f"    first item (truncated): {json.dumps(item, ensure_ascii=False)[:500]}")
    elif isinstance(data, dict):
        print(f"    dict with keys: {sorted(data.keys())}")
    else:
        print(f"    top-level type: {type(data).__name__}")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    root = Path(sys.argv[1])
    if not root.exists():
        print(f"{root} does not exist", file=sys.stderr)
        sys.exit(1)

    print(f"Tree under {root}:\n")
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        size = path.stat().st_size
        total_bytes += size
        rel = path.relative_to(root)
        print(f"  {rel}  ({size / 1024:.1f} KB)")
        if path.suffix == ".json":
            describe_json(path)

    print(f"\nTotal: {total_bytes / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()

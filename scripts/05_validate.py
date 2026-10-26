#!/usr/bin/env python
"""
QA pass for a scope: every question has exactly one non-empty .md file, no
missing/duplicate q_id, frontmatter is present and complete, every image
reference has a caption blockquote under it. Mirrors the spirit of Stage 1's
verification_report.md. Writes qa_report.json + qa_report.md; does not
touch/delete anything (that's 06_cleanup.py, and only after this passes).

Usage:
    python scripts/05_validate.py --pilot
    python scripts/05_validate.py --year 2026_jan
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import config, io_utils, scope  # noqa: E402

_IMG_LINE = re.compile(r"!\[\]\([^)]*\)")
_CAPTION_LINE = "> Image content:"


def validate_one(sy: scope.ScopeYear) -> dict:
    checks: list[dict] = []

    def check(status: str, name: str, detail: str = ""):
        checks.append({"status": status, "check": name, "detail": detail})

    state = scope.load_state(sy)
    if not state.get("split_done"):
        check("FAIL", "split stage completed", "run 04_split_questions.py first")
        return {"year": sy.year_name, "result": "FAIL", "checks": checks}

    expected_ids = {row["q_id"] for row in sy.rows}
    if len(expected_ids) != len(sy.rows):
        check("FAIL", "no duplicate q_id in questions_index", f"{len(sy.rows)} rows, {len(expected_ids)} unique")
    else:
        check("PASS", "no duplicate q_id in questions_index")

    expected_files = {io_utils.sanitize_q_id(qid): qid for qid in expected_ids}
    actual_files = {p.stem: p for p in sy.questions_md_dir.glob("*.md")} if sy.questions_md_dir.exists() else {}

    missing = set(expected_files) - set(actual_files)
    extra = set(actual_files) - set(expected_files)
    if missing:
        check("FAIL", "one .md per question, none missing", f"{len(missing)} missing: {sorted(missing)[:10]}")
    else:
        check("PASS", "one .md per question, none missing", f"{len(expected_files)} files")
    if extra:
        check("WARN", "no unexpected extra .md files", f"{len(extra)} extra: {sorted(extra)[:10]}")
    else:
        check("PASS", "no unexpected extra .md files")

    empty, missing_frontmatter, missing_qno, orphan_images = [], [], [], []
    for stem, qid in expected_files.items():
        path = actual_files.get(stem)
        if path is None:
            continue
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            empty.append(stem)
            continue
        if not text.startswith("---"):
            missing_frontmatter.append(stem)
        row = next(r for r in sy.rows if r["q_id"] == qid)
        if f"{row['q_no']}" not in text.split("---", 2)[-1][:2000] and f'"{qid}"' not in text:
            # cheap sanity check: the question number should appear somewhere
            # near the top of the body, not buried proof of correctness but
            # catches a wildly mismatched slice
            missing_qno.append(stem)
        for img_match in _IMG_LINE.finditer(text):
            tail = text[img_match.end():img_match.end() + 200]
            if _CAPTION_LINE not in tail:
                orphan_images.append(stem)
                break

    check("PASS" if not empty else "FAIL", "no empty .md files", f"{len(empty)} empty" if empty else "")
    check("PASS" if not missing_frontmatter else "FAIL", "every .md has YAML frontmatter",
          f"{len(missing_frontmatter)} missing" if missing_frontmatter else "")
    check("PASS" if not missing_qno else "WARN", "q_no visible near top of body",
          f"{len(missing_qno)} suspicious: {missing_qno[:10]}" if missing_qno else "")
    check("PASS" if not orphan_images else "FAIL", "every image has a caption blockquote",
          f"{len(orphan_images)} orphaned: {orphan_images[:10]}" if orphan_images else "")

    split_warnings_path = sy.out_dir / "split_warnings.json"
    n_split_warnings = len(json.load(open(split_warnings_path, encoding="utf-8"))) if split_warnings_path.exists() else 0
    check("PASS" if not n_split_warnings else "WARN", "no start-marker-not-found fallbacks during split",
          f"{n_split_warnings} question(s) fell back to the full page range" if n_split_warnings else "")

    failures = sum(1 for c in checks if c["status"] == "FAIL")
    result = "FAIL" if failures else ("WARN" if any(c["status"] == "WARN" for c in checks) else "PASS")
    return {"year": sy.year_name, "result": result, "checks": checks}


def render_markdown(report: dict) -> str:
    lines = [f"# Validation report - {report['scope']}", ""]
    for yr in report["years"]:
        lines.append(f"## {yr['year']}: **{yr['result']}**")
        lines.append("")
        lines.append("| Status | Check | Detail |")
        lines.append("|---|---|---|")
        for c in yr["checks"]:
            lines.append(f"| {c['status']} | {c['check']} | {c['detail']} |")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true")
    g.add_argument("--year")
    g.add_argument("--all", action="store_true")
    args = ap.parse_args()

    scopes = [config.PILOT_SCOPE] if args.pilot else (
        [y.name for y in config.year_dirs()] if args.all else [args.year]
    )

    for s in scopes:
        years_report = [validate_one(sy) for sy in scope.iter_scope(s)]
        out_dir = config.scope_output_dir(s)
        out_dir.mkdir(parents=True, exist_ok=True)
        report = {"scope": s, "years": years_report}
        json.dump(report, open(out_dir / "qa_report.json", "w", encoding="utf-8"), indent=2)
        (out_dir / "qa_report.md").write_text(render_markdown(report), encoding="utf-8")

        for yr in years_report:
            print(f"[{s}/{yr['year']}] {yr['result']}")
            for c in yr["checks"]:
                if c["status"] != "PASS":
                    print(f"    {c['status']}: {c['check']} - {c['detail']}")

        for sy in scope.iter_scope(s):
            yr_result = next(r for r in years_report if r["year"] == sy.year_name)
            scope.save_state(sy, validated=(yr_result["result"] != "FAIL"), qa_result=yr_result["result"])


if __name__ == "__main__":
    main()

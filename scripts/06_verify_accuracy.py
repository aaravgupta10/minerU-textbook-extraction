#!/usr/bin/env python
"""
Content-ACCURACY verification, distinct from 05_validate.py's structural QA
(file counts, non-empty, frontmatter present). This checks whether the
extracted text is actually *right*:

  1. Independent cross-check: re-extracts each question's text straight from
     content.pdf via PyMuPDF (no MinerU involved) using the same boundary-
     slicing algorithm, and scores how well it agrees with the pipeline's
     actual output. Low agreement flags a likely MinerU mis-parse or a
     slicing bug - see common/reference_extract.py for why this is a
     genuine independent signal, not the pipeline checking itself.
  2. Boundary-leak check: the next question's marker shouldn't appear in
     this question's body.
  3. Answer/solution marker check: if profile.json's marker_regexes (e.g.
     "Correct Answer:") show up in the independent reference extraction but
     not in the pipeline's output, the solution was likely truncated.
  4. LaTeX/brace balance heuristic on the pipeline's output.
  5. Image caption sanity: empty/placeholder captions, refusal-shaped
     captions, and identical captions reused across different images
     (a sign Bedrock returned a stuck/templated response).
  6. Human spot-check package: renders each flagged question's original
     page(s) to PNG (plus a random sample of non-flagged ones for a
     full-year run - the pilot renders everything, it's small on purpose)
     and writes review.md, mirroring Stage 1's own verification_report.md
     "spot-check list for a human reviewer" pattern.

Needs no GPU/Bedrock - runs entirely on content.pdf + the already-produced
questions_md/ + captions.json.

Usage:
    python scripts/06_verify_accuracy.py --pilot
    python scripts/06_verify_accuracy.py --year 2026_jan
"""
import argparse
import difflib
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import config, io_utils, mineru_adapter, pdf_utils, reference_extract, scope, slicing  # noqa: E402

_REFUSAL_HINTS = ("i cannot", "i'm unable", "i am unable", "as an ai", "cannot assist")


def _pipeline_text_only(blocks_in_range: list[dict], question_regex: re.Pattern,
                         q_no: int, is_last_in_section: bool) -> str:
    """MinerU's own text-only view (no image captions) of this question,
    sliced the same way 04_split_questions.py slices for the real .md -
    used as the comparison baseline against reference_extract's PyMuPDF-only
    text, since neither side ever includes image content. Deliberately NOT
    a regex re-parse of the rendered .md: an earlier version tried to strip
    `> Image content: ...` blocks back out of the final markdown, but that
    regex only stripped the first paragraph and left multi-paragraph
    structured captions (which the prompt now asks for) leaking into the
    similarity comparison - see progress.md."""
    start = slicing.find_marker(blocks_in_range, question_regex, q_no)
    sliced = blocks_in_range if start is None else slicing.slice_blocks(
        blocks_in_range, start, slicing.find_end_marker(blocks_in_range, question_regex, q_no, is_last_in_section))
    text = " ".join(b["text"] for b in sliced if b["type"] == "text" and b.get("text"))
    return re.sub(r"\s+", " ", text).strip()


def _similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _brace_balance_ok(text: str) -> bool:
    checks = [
        text.count("$") % 2 == 0,
        text.count("\\(") == text.count("\\)"),
        abs(text.count("{") - text.count("}")) <= 2,
    ]
    return all(checks)


def _has_any_marker(text: str, marker_regexes: list[re.Pattern]) -> bool:
    return any(p.search(text) for p in marker_regexes)


def verify_one(sy: scope.ScopeYear) -> dict:
    profile = io_utils.read_profile(sy.year_dir)
    question_regex = re.compile(profile["question_regex"])
    marker_regexes = [re.compile(p) for p in profile.get("marker_regexes", [])]
    next_marker_re = re.compile(profile["question_regex"])

    captions = {}
    captions_path = sy.captions_dir / "captions.json"
    if captions_path.exists():
        captions = json.load(open(captions_path, encoding="utf-8"))
    caption_to_images: dict[str, list[str]] = {}
    for img_path, cap in captions.items():
        if cap:
            caption_to_images.setdefault(cap.strip().lower(), []).append(img_path)

    by_page = mineru_adapter.blocks_by_content_page(sy.mineru_output_md, sy.page_map())

    rows_out = []
    for row in sy.rows:
        md_path = sy.questions_md_dir / f"{io_utils.sanitize_q_id(row['q_id'])}.md"
        flags = []
        if not md_path.exists():
            rows_out.append({"q_id": row["q_id"], "flags": ["missing_md_file"], "similarity": 0.0})
            continue

        md_text = md_path.read_text(encoding="utf-8")
        pages = range(row["content_page"], row["page_end"] + 1)
        blocks_in_range = [b for p in pages for b in by_page.get(p, [])]
        pipeline_text = _pipeline_text_only(blocks_in_range, question_regex, row["q_no"],
                                             row.get("is_last_in_section", False))
        ref_text, ref_start_found = reference_extract.reference_slice(sy, row, question_regex)
        ref_norm = re.sub(r"\s+", " ", ref_text).strip()

        similarity = _similarity(ref_norm.lower(), pipeline_text.lower())
        if similarity < config.ACCURACY_SIMILARITY_FAIL:
            flags.append(f"low_similarity({similarity:.2f})")
        elif similarity < config.ACCURACY_SIMILARITY_WARN:
            flags.append(f"marginal_similarity({similarity:.2f})")

        if not ref_start_found:
            flags.append("reference_start_marker_not_found")

        leak_hits = [int(m.group(1)) for m in next_marker_re.finditer(pipeline_text)
                     if int(m.group(1)) != row["q_no"]]
        if leak_hits:
            flags.append(f"boundary_leak(other_q_no_present={sorted(set(leak_hits))})")

        if marker_regexes and _has_any_marker(ref_norm, marker_regexes) and not _has_any_marker(pipeline_text, marker_regexes):
            flags.append("answer_marker_missing_vs_reference")

        if not _brace_balance_ok(md_text):
            flags.append("latex_brace_imbalance")

        img_matches = re.findall(r"!\[\]\(([^)]*)\)", md_text)
        for img_path in img_matches:
            cap = captions.get(img_path)
            if cap is None or cap == "":
                flags.append(f"missing_caption({img_path})")
            elif cap == "[image description unavailable]":
                flags.append(f"caption_generation_failed({img_path})")
            else:
                if len(cap.strip()) < 15:
                    flags.append(f"caption_too_short({img_path})")
                if any(hint in cap.lower() for hint in _REFUSAL_HINTS):
                    flags.append(f"caption_looks_like_refusal({img_path})")
                dupes = caption_to_images.get(cap.strip().lower(), [])
                if len(dupes) > 1 and img_path in dupes:
                    flags.append(f"duplicate_caption_shared_with({[d for d in dupes if d != img_path]})")

        rows_out.append({
            "q_id": row["q_id"], "year": sy.year_name, "subject": row["subject_label"],
            "q_no": row["q_no"], "paper": row["paper"],
            "content_page": row["content_page"], "page_end": row["page_end"],
            "similarity": round(similarity, 3), "flags": flags,
        })

    n_flagged = sum(1 for r in rows_out if r["flags"])
    result = "FAIL" if any("low_similarity" in f or f == "missing_md_file" for r in rows_out for f in r["flags"]) \
        else ("WARN" if n_flagged else "PASS")
    return {"year": sy.year_name, "result": result, "n_questions": len(rows_out),
            "n_flagged": n_flagged, "rows": rows_out}


def build_review_package(sy: scope.ScopeYear, year_report: dict):
    review_dir = sy.out_dir / "review"
    pages_dir = review_dir / "pages"

    flagged = [r for r in year_report["rows"] if r["flags"]]
    unflagged = [r for r in year_report["rows"] if not r["flags"]]

    if sy.scope == config.PILOT_SCOPE:
        sample = unflagged  # render everything, pilot is small on purpose
    else:
        rng = random.Random(config.PILOT_SEED)
        sample = rng.sample(unflagged, min(config.ACCURACY_RANDOM_SAMPLE_SIZE, len(unflagged)))

    to_render = flagged + sample
    lines = [f"# Human spot-check - {sy.scope}/{sy.year_name}", "",
             f"{len(flagged)} flagged question(s), {len(sample)} random sample for comparison.",
             "Open each rendered page image next to its .md and confirm the text/answer/image "
             "actually match what's printed on the page.", "",
             "| q_id | subject | q_no | paper | similarity | flags | page image | .md |",
             "|---|---|---|---|---|---|---|---|"]

    for r in to_render:
        row = next(row for row in sy.rows if row["q_id"] == r["q_id"])
        content_pages = list(range(row["content_page"], row["page_end"] + 1))
        working_pages = sy.working_pages_for(row["content_page"], row["page_end"])
        stem = io_utils.sanitize_q_id(r["q_id"])
        # Renders from working_pdf (identical to content.pdf for a full-year
        # scope; the small pre-built subset for the pilot) so this doesn't
        # require the full content.pdf to be present.
        rendered = pdf_utils.render_pages(sy.working_pdf, working_pages, pages_dir, stem, config.ACCURACY_RENDER_DPI)
        img_links = " ".join(f"[p{cp}](pages/{p_path.name})" for cp, p_path in zip(content_pages, rendered))
        md_link = f"questions_md/{stem}.md"
        flags_str = "; ".join(r["flags"]) if r["flags"] else "-"
        # q_id looks like "S04|Physics|Q009" - the literal pipes would break
        # markdown table parsing (extra column separators) if embedded
        # as-is, so display the sanitized/underscored form instead.
        lines.append(f"| {stem} | {r.get('subject','')} | {r.get('q_no','')} | "
                      f"{row['paper']} | {r.get('similarity','')} | {flags_str} | {img_links} | {md_link} |")

    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "review.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[{sy.scope}/{sy.year_name}] review package: {len(to_render)} question(s) rendered -> "
          f"{review_dir / 'review.md'}")


def render_summary(report: dict) -> str:
    lines = [f"# Accuracy verification - {report['scope']}", ""]
    for yr in report["years"]:
        lines.append(f"## {yr['year']}: **{yr['result']}** "
                      f"({yr['n_flagged']}/{yr['n_questions']} flagged)")
        lines.append("")
        lines.append("| q_id | subject | q_no | similarity | flags |")
        lines.append("|---|---|---|---|---|")
        for r in yr["rows"]:
            if r["flags"]:
                # Same pipe-in-q_id escaping issue as build_review_package.
                safe_id = io_utils.sanitize_q_id(r["q_id"])
                lines.append(f"| {safe_id} | {r.get('subject','')} | {r.get('q_no','')} | "
                              f"{r.get('similarity','')} | {'; '.join(r['flags'])} |")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true")
    g.add_argument("--year")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--no-review", action="store_true", help="Skip rendering the human spot-check package")
    args = ap.parse_args()

    scopes = [config.PILOT_SCOPE] if args.pilot else (
        [y.name for y in config.year_dirs()] if args.all else [args.year]
    )

    for s in scopes:
        years_report = []
        for sy in scope.iter_scope(s):
            state = scope.load_state(sy)
            if not state.get("split_done"):
                print(f"[{s}/{sy.year_name}] SKIP: run 04_split_questions.py first")
                continue
            yr = verify_one(sy)
            years_report.append(yr)
            print(f"[{s}/{sy.year_name}] {yr['result']} - {yr['n_flagged']}/{yr['n_questions']} flagged")
            if not args.no_review:
                build_review_package(sy, yr)
            scope.save_state(sy, accuracy_result=yr["result"], accuracy_n_flagged=yr["n_flagged"])

        if not years_report:
            continue
        out_dir = config.scope_output_dir(s)
        report = {"scope": s, "years": years_report}
        json.dump(report, open(out_dir / "accuracy_report.json", "w", encoding="utf-8"), indent=2)
        (out_dir / "accuracy_report.md").write_text(render_summary(report), encoding="utf-8")
        print(f"[{s}] accuracy_report.md written -> {out_dir / 'accuracy_report.md'}")


if __name__ == "__main__":
    main()

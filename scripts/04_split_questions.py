#!/usr/bin/env python
"""
Slices a year's (or the pilot's) parsed MinerU output into one markdown file
per question, using questions_index.csv's page ranges to narrow down to a
handful of pages and profile.json's question_regex to find the exact start/
end boundary within them - text-boundary slicing, not raw PDF-page slicing,
so the one-page overlap between consecutive questions (Q1: pages 1-2, Q2:
pages 2-3) doesn't duplicate or truncate content. Image blocks are rendered
with their Bedrock caption as a blockquote underneath.

Usage:
    python scripts/04_split_questions.py --pilot
    python scripts/04_split_questions.py --year 2026_jan
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import config, io_utils, mineru_adapter, scope, slicing  # noqa: E402


def _block_text_for_render(block: dict, captions: dict) -> str:
    if block["type"] == "image":
        rel = mineru_adapter.image_relpath(block["locator"])
        caption = captions.get(rel)
        if caption is None:
            caption = "[image description unavailable]"
        return f"![]({rel})\n\n> Image content: {caption}"
    return block.get("text") or ""


def build_markdown(row: dict, blocks_in_range: list[dict], captions: dict,
                    question_regex: re.Pattern, warnings: list[str], report_row: dict) -> str:
    start = slicing.find_marker(blocks_in_range, question_regex, row["q_no"])
    report_row["start_marker_found"] = start is not None
    if start is None:
        warnings.append(f"{row['q_id']}: start marker 'Q. {row['q_no']}' not found in "
                         f"content pages {row['content_page']}-{row['page_end']}; "
                         f"keeping the full page range as a fallback")
        sliced = blocks_in_range
    else:
        end = slicing.find_end_marker(blocks_in_range, question_regex, row["q_no"],
                                       row.get("is_last_in_section", False))
        report_row["end_marker_found"] = end is not None
        sliced = slicing.slice_blocks(blocks_in_range, start, end)

    image_blocks = [b for b in sliced if b["type"] == "image"]
    report_row["n_images"] = len(image_blocks)
    report_row["n_captions_missing"] = sum(
        1 for b in image_blocks if captions.get(mineru_adapter.image_relpath(b["locator"])) is None
    )

    frontmatter = {
        "q_id": row["q_id"],
        "year": row["year"],
        "section_index": row["section_index"],
        "subject": row["subject_label"],
        "q_no": row["q_no"],
        "paper": row["paper"],
        "original_page": row["original_page"],
        "orig_page_end": row["orig_page_end"],
        "content_page": row["content_page"],
        "page_end": row["page_end"],
    }
    fm_lines = "\n".join(f'{k}: "{v}"' if isinstance(v, str) else f"{k}: {v}"
                          for k, v in frontmatter.items())
    body = "\n\n".join(_block_text_for_render(b, captions) for b in sliced
                        if _block_text_for_render(b, captions).strip())
    return f"---\n{fm_lines}\n---\n\n{body}\n"


def run_one(sy: scope.ScopeYear, force: bool):
    state = scope.load_state(sy)
    if state.get("split_done") and not force:
        print(f"[{sy.scope}/{sy.year_name}] split already done, skipping (--force to redo)")
        return
    if not state.get("mineru_done"):
        print(f"[{sy.scope}/{sy.year_name}] SKIP: mineru hasn't run yet")
        return

    profile = io_utils.read_profile(sy.year_dir)
    question_regex = re.compile(profile["question_regex"])
    captions = {}
    captions_path = sy.captions_dir / "captions.json"
    if captions_path.exists():
        captions = json.load(open(captions_path, encoding="utf-8"))
    elif state.get("n_images", 0) > 0:
        print(f"[{sy.scope}/{sy.year_name}] WARNING: images exist but no captions.json - "
              f"run 03_caption_images_bedrock.py first")

    by_page = mineru_adapter.blocks_by_content_page(sy.mineru_output_md, sy.page_map())

    sy.questions_md_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    report: list[dict] = []
    written = 0
    for row in sy.rows:
        pages = range(row["content_page"], row["page_end"] + 1)
        blocks_in_range = [b for p in pages for b in by_page.get(p, [])]
        report_row = {"q_id": row["q_id"]}
        md = build_markdown(row, blocks_in_range, captions, question_regex, warnings, report_row)
        out_path = sy.questions_md_dir / f"{io_utils.sanitize_q_id(row['q_id'])}.md"
        out_path.write_text(md, encoding="utf-8")
        report.append(report_row)
        written += 1

    json.dump(report, open(sy.out_dir / "split_report.json", "w", encoding="utf-8"), indent=2)
    if warnings:
        json.dump(warnings, open(sy.out_dir / "split_warnings.json", "w", encoding="utf-8"), indent=2)
        print(f"[{sy.scope}/{sy.year_name}] {len(warnings)} warning(s) - see split_warnings.json")

    scope.save_state(sy, split_done=True, n_questions_written=written)
    print(f"[{sy.scope}/{sy.year_name}] wrote {written} question .md files -> {sy.questions_md_dir}")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true")
    g.add_argument("--year")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    scopes = [config.PILOT_SCOPE] if args.pilot else (
        [y.name for y in config.year_dirs()] if args.all else [args.year]
    )
    for s in scopes:
        for sy in scope.iter_scope(s):
            run_one(sy, args.force)


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""
Picks the pilot question set (default 30) before we spend any GPU/Bedrock
budget on the full ~5,775-question corpus. Deliberately samples to stress
the parts of the pipeline that are new or risky:

  - 2026_jan and 2026_april: proves the recovered shift labels (Step 0)
    actually land on the right questions, across multiple shifts each.
  - multi-page questions (page_end > content_page): proves the
    boundary-overlap slicing logic doesn't leak text from the neighboring
    question that shares a page.
  - image-bearing questions: proves the MinerU -> Bedrock caption ->
    reinjection path.
  - text-only questions: proves we're not sending everything to Bedrock
    needlessly (cost/latency).
  - all 3 subjects.

Runs entirely on PyMuPDF, no GPU/MinerU/Bedrock needed. Safe to run on a
laptop.

Usage:
    python scripts/01_select_pilot.py
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import config, io_utils, pdf_utils  # noqa: E402

# year -> how many pilot questions to draw from it. 2026 years get more
# weight since they're the ones exercising the label-recovery fix.
YEAR_QUOTAS = {
    "2026_jan": 6,
    "2026_april": 5,
    "2018": 3,
    "2020_jan": 3,
    "2020_september": 3,
    "2022_june": 4,
    "2022_july": 3,
    "2024_april": 3,
}


def annotate_rows(year_dir: Path, rows: list[dict]) -> list[dict]:
    img_counts = pdf_utils.page_image_counts(year_dir / "content.pdf")
    n_pages = len(img_counts)
    for r in rows:
        pages = range(r["content_page"], r["page_end"] + 1)
        r["has_image"] = any(
            0 <= (p - 1) < n_pages and img_counts[p - 1] > 0 for p in pages
        )
        r["multipage"] = r["page_end"] > r["content_page"]
    return rows


def pick_for_year(rows: list[dict], quota: int, rng: random.Random) -> list[dict]:
    by_subject: dict[str, list[dict]] = {}
    for r in rows:
        by_subject.setdefault(r["subject_label"], []).append(r)
    for bucket in by_subject.values():
        rng.shuffle(bucket)

    picked: list[dict] = []
    picked_counts = {subj: 0 for subj in by_subject}
    have_image = have_multipage = False

    while len(picked) < quota and any(by_subject.values()):
        # Always draw from whichever non-empty subject bucket is currently
        # most under-represented, so no single subject can dominate.
        subj = min(
            (s for s, bucket in by_subject.items() if bucket),
            key=lambda s: picked_counts[s],
        )
        bucket = by_subject[subj]

        chosen = None
        if not have_image:
            chosen = next((r for r in bucket if r["has_image"]), None)
        if chosen is None and not have_multipage:
            chosen = next((r for r in bucket if r["multipage"]), None)
        if chosen is None:
            chosen = bucket[-1]

        bucket.remove(chosen)
        picked.append(chosen)
        picked_counts[subj] += 1
        have_image = have_image or chosen["has_image"]
        have_multipage = have_multipage or chosen["multipage"]

    return picked[:quota]


def main():
    rng = random.Random(config.PILOT_SEED)
    all_years = {y.name: y for y in config.year_dirs()}
    selection = []

    for year_name, quota in YEAR_QUOTAS.items():
        year_dir = all_years.get(year_name)
        if year_dir is None:
            print(f"WARNING: year '{year_name}' not found under {config.DELIVERABLES_DIR}, skipping")
            continue
        overrides = io_utils.read_label_overrides(year_dir.name)
        rows = io_utils.read_questions_index(year_dir, overrides)
        rows = annotate_rows(year_dir, rows)

        total_sections = len({r["section_index"] for r in rows})

        picked: list[dict] = []
        if overrides and len(overrides) < total_sections:
            # A *partial* gap (e.g. 2026_april's first shift): force one pick
            # from each recovered section specifically, so the pilot proves
            # the fix landed on the previously-blank section rather than just
            # a section that was already labeled. For a *fully* blank year
            # (2026_jan, every section recovered) this isn't meaningful -
            # normal balanced picking already spreads across shifts/dates.
            for section_idx in sorted(overrides):
                candidates = [r for r in rows if r["section_index"] == section_idx and r not in picked]
                if candidates:
                    picked.append(rng.choice(candidates))
                if len(picked) >= quota:
                    break
        remaining_pool = [r for r in rows if r not in picked]
        picked.extend(pick_for_year(remaining_pool, quota - len(picked), rng))

        for r in picked:
            r["year"] = year_name
        selection.extend(picked)

    out_dir = config.scope_output_dir(config.PILOT_SCOPE)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "pilot_selection.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(selection, f, indent=2)

    n_img = sum(1 for r in selection if r["has_image"])
    n_multi = sum(1 for r in selection if r["multipage"])
    subjects = sorted({r["subject_label"] for r in selection})
    years = sorted({r["year"] for r in selection})

    print(f"Selected {len(selection)} pilot questions -> {out_path}")
    print(f"  years: {years}")
    print(f"  subjects: {subjects}")
    print(f"  image-bearing: {n_img}, multi-page: {n_multi}")
    print()
    print(f"{'q_id':<22}{'year':<16}{'subject':<12}{'pages':<8}{'img':<5}{'paper'}")
    for r in sorted(selection, key=lambda r: (r["year"], r["section_index"], r["q_no"])):
        pages = f"{r['content_page']}-{r['page_end']}"
        print(f"{r['q_id']:<22}{r['year']:<16}{r['subject_label']:<12}{pages:<8}"
              f"{'Y' if r['has_image'] else '.':<5}{r['paper']}")


if __name__ == "__main__":
    main()

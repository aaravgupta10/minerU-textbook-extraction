"""
Recovers shift/date labels that Stage 1 left blank (`paper: ""` in
sections.json) for 2026_jan (all sections) and 2026_april (its first shift).

Root cause: the table-of-contents / shift-divider pages that named each
shift were correctly classified as ads and pulled out of content.pdf - but
they were the *only* place the label text lived, and Stage 1 kept them
in removed_ads.pdf rather than deleting them. So the fix is deterministic:
read removed_ads.pdf, find the (label, start_page) pairs, and match each
blank section to the pair whose start_page is the closest one at-or-before
that section's original_page_start.
"""
import json
from pathlib import Path

from . import config, pdf_utils

_MIN_TOC_ENTRIES = 2  # a real ToC page has at least this many label/page pairs


def _extract_label_page_pairs(text: str) -> list[tuple[str, int]]:
    """Alternating-line parser: a label line immediately followed by a
    line that's just a page number. Matches both observed formats:
        '21st January Shift 1 Question Paper with Solution' / '3'
        'JEE MAIN 2nd April 1st Shift'                       / '3'
    """
    lines = [ln.strip() for ln in text.splitlines()]
    pairs = []
    i = 0
    while i < len(lines) - 1:
        label, nxt = lines[i], lines[i + 1]
        if label and nxt.isdigit() and not label.isdigit():
            pairs.append((label, int(nxt)))
            i += 2
        else:
            i += 1
    return pairs


def _find_toc(removed_ads_pdf: Path) -> list[tuple[str, int]]:
    """The page in removed_ads.pdf with the most label/page pairs is the
    authoritative table of contents."""
    best: list[tuple[str, int]] = []
    for text in pdf_utils.all_page_texts(removed_ads_pdf):
        pairs = _extract_label_page_pairs(text)
        if len(pairs) > len(best):
            best = pairs
    return sorted(best, key=lambda kv: kv[1])


def recover_labels(year_dir: Path) -> dict:
    """
    Returns {"labels": {section_index: label}, "unmatched": [...], "toc": [...]}
    and writes it to output/<year>/label_overrides.json. No-ops (empty
    labels dict) if every section already has a paper label.
    """
    sections = json.load(open(year_dir / "sections.json", encoding="utf-8"))
    blank = [s for s in sections if not s["paper"]]

    result = {"labels": {}, "unmatched": [], "toc": []}
    out_path = config.OUTPUT_DIR / year_dir.name / "label_overrides.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not blank:
        json.dump(result, open(out_path, "w", encoding="utf-8"), indent=2)
        return result

    removed_ads_pdf = year_dir / "removed_ads.pdf"
    if not removed_ads_pdf.exists():
        raise FileNotFoundError(
            f"{year_dir.name}: {len(blank)} sections have no paper label and "
            f"removed_ads.pdf is missing, so labels can't be recovered."
        )

    toc = _find_toc(removed_ads_pdf)
    result["toc"] = toc
    if len(toc) < _MIN_TOC_ENTRIES:
        raise ValueError(
            f"{year_dir.name}: only found {len(toc)} label/page pairs in "
            f"removed_ads.pdf - not enough to trust as a table of contents. "
            f"Inspect removed_ads.pdf manually for this year."
        )

    for s in blank:
        start = s["original_page_start"]
        candidates = [(label, page) for label, page in toc if page <= start]
        if not candidates:
            result["unmatched"].append(s["section_index"])
            continue
        label, _ = max(candidates, key=lambda kv: kv[1])
        result["labels"][str(s["section_index"])] = label

    json.dump(result, open(out_path, "w", encoding="utf-8"), indent=2)
    return result

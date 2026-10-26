"""
Readers for Stage 1's deliverables (questions_index.csv, sections.json,
page_map.csv, profile.json) plus the label-override patch produced by
00_recover_labels.py. Nothing here mutates a Stage 1 file.
"""
import csv
import json
import re
from pathlib import Path

from . import config

_INT_COLS = {"section_index", "q_no", "content_page", "page_end",
             "original_page", "orig_page_end"}


def read_sections(year_dir: Path):
    with open(year_dir / "sections.json", encoding="utf-8") as f:
        return json.load(f)


def read_page_map(year_dir: Path):
    """content_pdf_page (int) -> original_page (int)."""
    out = {}
    with open(year_dir / "page_map.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[int(row["content_pdf_page"])] = int(row["original_page"])
    return out


def read_profile(year_dir: Path):
    with open(year_dir / "profile.json", encoding="utf-8") as f:
        return json.load(f)


def read_label_overrides(year_dir_name: str):
    """{section_index (int): recovered label} if 00_recover_labels.py has run
    for this year, else {}."""
    path = config.OUTPUT_DIR / year_dir_name / "label_overrides.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {int(k): v for k, v in raw.get("labels", {}).items()}


def n_questions_per_section(year_dir: Path) -> dict[int, int]:
    return {s["section_index"]: s["n_questions"] for s in read_sections(year_dir)}


def read_questions_index(year_dir: Path, label_overrides: dict | None = None):
    """One dict per question row, with numeric columns cast, `paper`
    backfilled from label_overrides when Stage 1 left it blank, and
    `is_last_in_section` set from sections.json's n_questions. That last
    field matters for boundary slicing (see common/slicing.find_end_marker):
    numbering resets per section, so the last question in a section has no
    "q_no + 1" to search for, and Stage 1's page ranges let it legitimately
    share its final page with the next section's own "Q. 1" - confirmed as
    a real leak into 04_split_questions.py's output before this field
    existed, not just a theoretical edge case. Computed here (not derived
    from a ScopeYear's own .rows) so it's correct in BOTH the full-year
    scope AND the pilot scope, where .rows is only a small sample and can't
    be used to infer a section's true last question."""
    label_overrides = label_overrides or {}
    n_per_section = n_questions_per_section(year_dir)
    rows = []
    with open(year_dir / "questions_index.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for col in _INT_COLS:
                row[col] = int(row[col])
            if not row["paper"]:
                row["paper"] = label_overrides.get(row["section_index"], "")
            row["is_last_in_section"] = row["q_no"] == n_per_section.get(row["section_index"])
            rows.append(row)
    return rows


_SAFE_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def sanitize_q_id(q_id: str) -> str:
    """'S01|Physics|Q001' -> 'S01_Physics_Q001'"""
    return _SAFE_CHARS.sub("_", q_id.replace("|", "_")).strip("_")


def year_name(year_dir: Path) -> str:
    return year_dir.name

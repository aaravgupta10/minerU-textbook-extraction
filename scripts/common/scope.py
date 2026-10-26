"""
Unifies "run the full year" and "run just the pilot's questions for this
year" behind one interface, so 02/03/04/05/06 don't need separate code
paths. A "scope" is either:
    - a real year folder name, e.g. "2026_jan"  -> every question in it
    - "_pilot"                                   -> only the questions listed
                                                     in output/_pilot/pilot_selection.json,
                                                     grouped by year
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from . import config, io_utils, pdf_utils


@dataclass
class ScopeYear:
    scope: str          # "_pilot" or the year name itself
    year_name: str
    year_dir: Path
    rows: list          # question rows in scope for this year
    out_dir: Path        # output/<scope>/<year_name>/

    @property
    def source_pdf(self) -> Path:
        return self.year_dir / "content.pdf"

    @property
    def working_pdf(self) -> Path:
        """The PDF actually handed to MinerU. For a full-year scope this IS
        content.pdf (no copy needed); for the pilot it's a small subset."""
        if self.scope == self.year_name:  # full-year run
            return self.source_pdf
        return self.out_dir / "mineru_raw" / f"{self.year_name}_pilot_working.pdf"

    @property
    def mineru_out_dir(self) -> Path:
        """Scratch/log dir for this stage - NOT where MinerU's markdown
        output lives (that's mineru_output_md, a single file)."""
        return self.out_dir / "mineru_raw"

    @property
    def mineru_output_md(self) -> Path:
        """The single markdown file `mineru parse` writes for this year/pilot
        subset - confirmed 2026-09-24 that --output is a file path here, not
        a directory (see common/mineru_adapter.py)."""
        return self.mineru_out_dir / f"{self.year_name}_parsed.md"

    @property
    def captions_dir(self) -> Path:
        return self.out_dir / "captions"

    @property
    def images_dir(self) -> Path:
        """Where fetched image-block assets (via `mineru read --format
        image`) live permanently - a sibling of questions_md/, referenced
        from each question's .md as '../images/<file>.png' (see
        mineru_adapter.image_relpath). Kept outside mineru_raw/ so
        07_cleanup.py's debug-output deletion never touches it."""
        return self.out_dir / "images"

    @property
    def questions_md_dir(self) -> Path:
        return self.out_dir / "questions_md"

    @property
    def state_path(self) -> Path:
        return self.out_dir / "_state.json"

    def page_map(self) -> dict[int, int]:
        """working pdf page (1-indexed) -> content.pdf page (1-indexed)."""
        if self.scope == self.year_name:
            n_pages = fitz.open(self.source_pdf).page_count
            return {i: i for i in range(1, n_pages + 1)}
        return pdf_utils.load_working_page_map(self.working_pdf)

    def ensure_working_pdf(self):
        """No-op for a full-year scope. For the pilot, builds the subset PDF
        (once) from the union of this year's pilot rows' page ranges."""
        if self.scope == self.year_name:
            return
        if self.working_pdf.exists():
            return
        pages = set()
        for r in self.rows:
            pages.update(range(r["content_page"], r["page_end"] + 1))
        pdf_utils.build_working_pdf(self.source_pdf, sorted(pages), self.working_pdf)

    def working_pages_for(self, content_page_start: int, content_page_end: int) -> list[int]:
        """Translate a content.pdf page range into the corresponding pages of
        self.working_pdf - identity for a full-year scope, a lookup for a
        pilot subset. Used so accuracy verification (reference re-extraction,
        the rendered spot-check images) reads working_pdf rather than the
        full content.pdf, which a lean pilot upload may not even carry."""
        page_map = self.page_map()  # working_page -> content_page
        inverse = {v: k for k, v in page_map.items()}
        return [inverse[p] for p in range(content_page_start, content_page_end + 1) if p in inverse]


def _load_state(path: Path) -> dict:
    if path.exists():
        return json.load(open(path, encoding="utf-8"))
    return {}


def save_state(sy: ScopeYear, **updates):
    state = _load_state(sy.state_path)
    state.update(updates)
    sy.out_dir.mkdir(parents=True, exist_ok=True)
    json.dump(state, open(sy.state_path, "w", encoding="utf-8"), indent=2)


def load_state(sy: ScopeYear) -> dict:
    return _load_state(sy.state_path)


def iter_scope(scope: str) -> list[ScopeYear]:
    if scope == config.PILOT_SCOPE:
        sel_path = config.scope_output_dir(config.PILOT_SCOPE) / "pilot_selection.json"
        if not sel_path.exists():
            raise FileNotFoundError(
                f"{sel_path} not found - run scripts/01_select_pilot.py first."
            )
        selection = json.load(open(sel_path, encoding="utf-8"))
        by_year: dict[str, list] = {}
        for r in selection:
            by_year.setdefault(r["year"], []).append(r)
        # Deliberately does NOT require content.pdf to exist: a lean pilot
        # upload only needs each year's profile.json + the pre-built working
        # PDF subset, not the full ~500MB of content.pdf across 8 years.
        out = []
        for year_name, rows in sorted(by_year.items()):
            year_dir = config.DELIVERABLES_DIR / year_name
            out_dir = config.scope_output_dir(config.PILOT_SCOPE) / year_name
            out.append(ScopeYear(config.PILOT_SCOPE, year_name, year_dir, rows, out_dir))
        return out

    all_years = {y.name: y for y in config.year_dirs()}
    if scope not in all_years:
        raise ValueError(f"Unknown scope '{scope}': not a year folder and not '{config.PILOT_SCOPE}'")
    year_dir = all_years[scope]
    overrides = io_utils.read_label_overrides(year_dir.name)
    rows = io_utils.read_questions_index(year_dir, overrides)
    out_dir = config.scope_output_dir(scope)
    return [ScopeYear(scope, scope, year_dir, rows, out_dir)]

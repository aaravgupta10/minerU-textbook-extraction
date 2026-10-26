"""
Runs MinerU 4.0.7's `parse` command (against its local `managed` GPU server)
and parses the single markdown file it produces into an ordered block list.

Calibrated against the REAL installed CLI on the AWS box on 2026-09-24/25
(see progress.md "On the real AWS box" entries) - this replaced an earlier
guess based on the old opendatalab/MinerU vlm-engine CLI, which does not
apply to this version. Confirmed real shape:

`mineru parse <pdf> --pages all --output <path> --tier standard` writes ONE
markdown file (output path is a FILE, not a directory) containing:
  - `<!-- page N of M -->` HTML comments marking page boundaries. N is
    1-indexed and matches the input PDF's own page order (i.e. the working
    PDF fed to this call) - translate to content.pdf page numbers via
    ScopeYear.page_map() as usual, no off-by-one adjustment needed.
  - inline image references as `![Image block](doc:<short_id>/tier:<tier>/
    page:<p>/block:<b>)` LOCATORS, not file paths - there is no images/
    folder from the parse call itself. Actual pixel data for one locator is
    fetched separately, confirmed working:
        mineru read "<locator>" --format image --output <path>
"""
import re
import subprocess
from pathlib import Path

from . import config

_PAGE_MARKER_RE = re.compile(r"<!--\s*page\s+(\d+)\s+of\s+\d+\s*-->")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((doc:[^)]+)\)")
_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9]+")


class MinerUOutputError(RuntimeError):
    pass


def run_mineru(pdf_path: Path, output_md_path: Path, log_path: Path) -> None:
    """Writes a single markdown file to output_md_path (NOT a directory)."""
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        config.MINERU_CLI, "parse", str(pdf_path),
        "--pages", "all",
        "--output", str(output_md_path),
        "--tier", config.MINERU_TIER,
        "--wait", str(config.MINERU_WAIT_SECONDS),
    ]
    if config.MINERU_FORCE_REPARSE:
        argv.append("--force")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as log_f:
        log_f.write(f"argv: {argv}\n\n")
        log_f.flush()
        result = subprocess.run(
            argv, stdout=log_f, stderr=subprocess.STDOUT,
            timeout=config.MINERU_TIMEOUT_SEC,
        )
    if result.returncode != 0:
        raise MinerUOutputError(f"mineru parse exited {result.returncode} on {pdf_path}. See {log_path}")
    if not output_md_path.exists():
        raise MinerUOutputError(
            f"mineru parse reported success (exit 0) but {output_md_path} was never created. See {log_path}"
        )


def load_blocks(output_md_path: Path) -> list[dict]:
    """
    Parses the single markdown file into an ordered block list:
        {"type": "text"|"image", "page_idx": int, "text": str|None, "locator": str|None}
    page_idx is 1-indexed, matching the working PDF's own page numbers.
    """
    text = output_md_path.read_text(encoding="utf-8")
    parts = _PAGE_MARKER_RE.split(text)
    # re.split with one capturing group -> [pre, page_num, chunk, page_num, chunk, ...]
    if len(parts) < 3:
        raise MinerUOutputError(
            f"No '<!-- page N of M -->' markers found in {output_md_path} - MinerU's "
            f"markdown output format may have changed since this adapter was calibrated."
        )

    blocks = []
    for i in range(1, len(parts), 2):
        page_num = int(parts[i])
        blocks.extend(_split_chunk_into_blocks(parts[i + 1], page_num))
    if not blocks:
        raise MinerUOutputError(f"{output_md_path} parsed but produced zero blocks")
    return blocks


def _split_chunk_into_blocks(chunk: str, page_num: int) -> list[dict]:
    out = []
    pos = 0
    for m in _IMAGE_RE.finditer(chunk):
        pre = chunk[pos:m.start()]
        if pre.strip():
            out.append({"type": "text", "page_idx": page_num, "text": pre, "locator": None})
        out.append({"type": "image", "page_idx": page_num, "text": None, "locator": m.group(1)})
        pos = m.end()
    tail = chunk[pos:]
    if tail.strip():
        out.append({"type": "text", "page_idx": page_num, "text": tail, "locator": None})
    return out


def content_page_for_block(block: dict, working_page_map: dict[int, int]) -> int | None:
    """Translate a block's (1-indexed, working-PDF-relative) page_idx into
    the real content.pdf page number."""
    if block["page_idx"] is None:
        return None
    return working_page_map.get(block["page_idx"])


def blocks_by_content_page(output_md_path: Path, working_page_map: dict[int, int]) -> dict[int, list[dict]]:
    """load_blocks() + translate to content.pdf page numbers + group by that
    page. Shared by 04_split_questions.py and 06_verify_accuracy.py so both
    slice against identically-prepared data - 06 needs MinerU's own
    text-only view of a question (no image captions) as the comparison
    baseline for its accuracy check, not a regex re-parse of the rendered
    .md, which breaks on multi-paragraph captions."""
    blocks = load_blocks(output_md_path)
    by_page: dict[int, list[dict]] = {}
    for b in blocks:
        cp = content_page_for_block(b, working_page_map)
        if cp is not None:
            by_page.setdefault(cp, []).append(b)
    return by_page


def image_filename(locator: str) -> str:
    """Stable filename for one image block's locator."""
    return _SAFE_CHARS_RE.sub("_", locator).strip("_") + ".png"


def image_relpath(locator: str) -> str:
    """The path used consistently as: the markdown image link in each
    question's .md, the captions.json key, and (resolved against
    ScopeYear.out_dir) the saved asset file location. Images live in
    out_dir/images/; questions_md/ is a sibling directory, hence '../images/'."""
    return f"../images/{image_filename(locator)}"


def fetch_image_asset(locator: str, out_path: Path) -> bytes:
    """Materializes one image block's pixel data via `mineru read --format
    image`, confirmed working against real output on 2026-09-24."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [config.MINERU_CLI, "read", locator, "--format", "image", "--output", str(out_path)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if result.returncode != 0 or not out_path.exists():
        raise MinerUOutputError(f"mineru read {locator!r} --format image failed: {result.stderr}")
    return out_path.read_bytes()

"""
Thin PyMuPDF (fitz) helpers. No MinerU/GPU dependency here, so these work
fine on a laptop for label recovery and pilot selection.
"""
import json
from pathlib import Path

import fitz  # PyMuPDF


def page_image_counts(pdf_path: Path) -> list[int]:
    """Number of embedded raster images on each page, 0-indexed list."""
    doc = fitz.open(pdf_path)
    try:
        return [len(doc[i].get_images(full=True)) for i in range(doc.page_count)]
    finally:
        doc.close()


def page_text(pdf_path: Path, page_index_0based: int) -> str:
    doc = fitz.open(pdf_path)
    try:
        return doc[page_index_0based].get_text()
    finally:
        doc.close()


def all_page_texts(pdf_path: Path) -> list[str]:
    doc = fitz.open(pdf_path)
    try:
        return [doc[i].get_text() for i in range(doc.page_count)]
    finally:
        doc.close()


def build_working_pdf(source_pdf_path: Path, page_numbers_1based: list[int],
                       out_path: Path) -> dict:
    """
    Write a new PDF containing exactly `page_numbers_1based` (1-indexed into
    source_pdf_path), deduplicated, in ascending order. Returns and also
    writes alongside out_path a sidecar map:
        {"working_page": source_page, ...}   (both 1-indexed)
    so downstream steps can translate MinerU's per-page output back to the
    real content.pdf page numbers regardless of how much of the source PDF
    was actually included in this working copy (full year vs. pilot subset).
    """
    ordered_unique = sorted(set(page_numbers_1based))
    src = fitz.open(source_pdf_path)
    try:
        out = fitz.open()
        for p in ordered_unique:
            out.insert_pdf(src, from_page=p - 1, to_page=p - 1)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out.save(out_path)
        out.close()
    finally:
        src.close()

    page_map = {str(i + 1): p for i, p in enumerate(ordered_unique)}
    with open(out_path.with_suffix(".pagemap.json"), "w", encoding="utf-8") as f:
        json.dump(page_map, f, indent=2)
    return page_map


def render_pages(pdf_path: Path, pages_1based: list[int], out_dir: Path,
                  stem: str, dpi: int = 150) -> list[Path]:
    """Renders the given pages to PNGs named '{stem}_p{page}.png'. Used for
    the human spot-check package in 07_verify_accuracy.py."""
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    out_paths = []
    try:
        for p in pages_1based:
            if not (1 <= p <= doc.page_count):
                continue
            pix = doc[p - 1].get_pixmap(dpi=dpi)
            out_path = out_dir / f"{stem}_p{p}.png"
            pix.save(out_path)
            out_paths.append(out_path)
    finally:
        doc.close()
    return out_paths


def load_working_page_map(working_pdf_path: Path) -> dict:
    """{working_page (int) -> source content.pdf page (int)}"""
    side = working_pdf_path.with_suffix(".pagemap.json")
    with open(side, encoding="utf-8") as f:
        raw = json.load(f)
    return {int(k): int(v) for k, v in raw.items()}

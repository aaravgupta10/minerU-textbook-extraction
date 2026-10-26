"""
An independent, MinerU-free re-extraction of each question's text, used
purely as an accuracy cross-check (see 07_verify_accuracy.py). Reuses the
same boundary-slicing algorithm as the real pipeline (common/slicing.py,
already verified against real data) but feeds it PyMuPDF's raw per-page
text instead of MinerU's parsed blocks.

This deliberately does NOT try to be a better extractor - PyMuPDF's raw
text layer loses table/formula structure that MinerU is specifically good
at. The point is narrower: if MinerU's output for a question and PyMuPDF's
raw text for the same page range disagree wildly (very low overlap, wrong
question number, truncated to almost nothing), that's a strong signal
something went wrong in either the MinerU parse or our own slicing - one
independent path corroborating the other is exactly what makes this a real
check rather than "the pipeline validating itself against itself".
"""
import re

from . import pdf_utils, slicing


def reference_slice(sy, row: dict, question_regex: re.Pattern) -> tuple[str, bool]:
    """Returns (text, start_marker_found). Reads sy.working_pdf, not the full
    content.pdf - identical file for a full-year scope, but for the pilot
    this lets accuracy verification run off the small pre-built subset PDF
    instead of requiring the full ~500MB of content.pdf across 8 years."""
    texts = pdf_utils.all_page_texts(sy.working_pdf)
    working_pages = sy.working_pages_for(row["content_page"], row["page_end"])
    blocks = [{"type": "text", "text": texts[p - 1]} for p in working_pages if 0 <= p - 1 < len(texts)]

    start = slicing.find_marker(blocks, question_regex, row["q_no"])
    if start is None:
        return "\n\n".join(b["text"] for b in blocks), False

    end = slicing.find_end_marker(blocks, question_regex, row["q_no"], row.get("is_last_in_section", False))
    sliced = slicing.slice_blocks(blocks, start, end)
    return "\n\n".join(b["text"] for b in sliced), True

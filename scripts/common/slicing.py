"""
The boundary-slicing algorithm shared by 04_split_questions.py (slices
MinerU's parsed blocks) and common/reference_extract.py (slices raw PyMuPDF
text as an independent cross-check, see 07_verify_accuracy.py). Operates on
a generic block list - anything with a "text" key - so it doesn't care
whether the blocks came from MinerU or straight PDF text extraction.

Verified against real 2018 content.pdf text (Q1/Q2/Q3, the real page-overlap
case): a question's slice stops exactly before the next question's marker
and starts exactly at its own, regardless of which page a solution image
happens to visually spill onto. See progress.md, 2026-09-24 entry.
"""
import re


def find_marker(blocks: list[dict], question_regex: re.Pattern, q_no: int):
    """First (block_index, match_start_char) where question_regex matches
    exactly this q_no, or None."""
    for i, b in enumerate(blocks):
        text = b.get("text")
        if not text:
            continue
        for m in question_regex.finditer(text):
            try:
                if int(m.group(1)) == q_no:
                    return i, m.start()
            except (IndexError, ValueError):
                continue
    return None


def find_end_marker(blocks: list[dict], question_regex: re.Pattern, q_no: int, is_last_in_section: bool):
    """End boundary for slicing: normally the next question's own marker
    (q_no + 1). But numbering resets per section (confirmed in every year's
    profile.json), so the LAST question of a section has no "q_no + 1" to
    find - and Stage 1's page ranges legitimately let a section's last
    question share its final page with the next section's first question
    (confirmed against real data: 2022_july section 21 ends at content page
    607, section 22 starts at page 607). Without this fallback, the last
    question in every section silently swallows the next section's "Q. 1"
    header - caught via the boundary_leak flag in 06_verify_accuracy.py on
    a pilot question, and confirmed as a real, then-unfixed systematic gap,
    not noise - see progress.md."""
    end = find_marker(blocks, question_regex, q_no + 1)
    if end is None and is_last_in_section:
        end = find_marker(blocks, question_regex, 1)
    return end


def slice_blocks(blocks: list[dict], start, end) -> list[dict]:
    start_i, start_off = start
    end_i = end[0] if end else len(blocks) - 1
    out = []
    for i in range(start_i, min(end_i, len(blocks) - 1) + 1):
        b = dict(blocks[i])
        text = b.get("text")
        if text is not None:
            lo = start_off if i == start_i else 0
            hi = end[1] if (end and i == end_i) else len(text)
            b["text"] = text[lo:hi]
        out.append(b)
    return out

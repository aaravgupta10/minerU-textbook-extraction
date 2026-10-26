# Verification report — ..\out\2026_april

**Result: WARN** — 17 pass, 1 warn, 0 fail

| Status | Check | Detail |
|---|---|---|
| PASS | all stage artifacts present |  |
| PASS | questions_index.csv column schema matches reference | q_id,section_index,paper,subject_label,q_no,content_page,page_end,original_page,orig_page_end |
| PASS | total pages = kept + ads | 568 = 565 + 3 |
| PASS | page_map.csv row count matches content.pdf page count | 565 rows |
| PASS | page_map.csv content_pdf_page is a contiguous 1..N run |  |
| PASS | page_map.csv original_page is strictly increasing, no dup |  |
| PASS | every question's content_page/page_end is inside content.pdf | 675 rows checked |
| PASS | page_end >= content_page for every question |  |
| PASS | original_page / orig_page_end match page_map.csv exactly | tag stage agrees with split stage on every row |
| PASS | no duplicate q_id (re-derived independently) | 675 ids, all unique |
| PASS | every section is a clean 1->N run (re-derived independently) | 27 sections |
| PASS | independent numbers match stage1_gate_report.json |  |
| WARN | shift/paper labels: every section labelled, count matches expected | 24/27 sections labelled, 8 distinct label(s), expected 9 shifts (27 sections / 3 subjects). Not a correctness bug (q_id doesn't depend on this) — a reporting gap, usually an unrecognised shift wording or a divider page removed as an ad. |
| PASS | no paper label spans a non-contiguous run of sections |  |
| PASS | orphan content pages match gate report (re-derived independently) | 0 orphan pages |
| PASS | pages/ image count matches content.pdf page count | 565 images |
| PASS | removed/ image count matches ad page count | 3 images |
| PASS | no render failures | render_failures.json absent |

## Spot-check list for a human reviewer

**Ad pages removed** (3): [1, 2, 3]

**REVIEW pages kept** (12): [63, 127, 189, 254, 255, 320, 368, 381, 382, 435, 444, 505]

**Random question sample** — open each `image_hint` and confirm subject/q_no/paper actually match what's printed on that original page:

| q_id | subject | q_no | paper | original_page | image_hint |
|---|---|---|---|---|---|
| S16|Physics|Q020 | Physics | 20 | 5th April 2nd Shift | 337 | pages/page_0337.png |
| S18|Mathematics|Q006 | Mathematics | 6 | 5th April 2nd Shift | 364 | pages/page_0364.png |
| S02|Chemistry|Q017 | Chemistry | 17 |  | 36 | pages/page_0036.png |
| S11|Chemistry|Q016 | Chemistry | 16 | 4th April 2nd Shift | 222 | pages/page_0222.png |
| S21|Mathematics|Q024 | Mathematics | 24 | 6th April 1st Shift | 442 | pages/page_0442.png |
| S20|Chemistry|Q023 | Chemistry | 23 | 6th April 1st Shift | 422 | pages/page_0422.png |

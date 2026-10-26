# Verification report — ..\out\2020_september

**Result: PASS** — 18 pass, 0 warn, 0 fail

| Status | Check | Detail |
|---|---|---|
| PASS | all stage artifacts present |  |
| PASS | questions_index.csv column schema matches reference | q_id,section_index,paper,subject_label,q_no,content_page,page_end,original_page,orig_page_end |
| PASS | total pages = kept + ads | 667 = 666 + 1 |
| PASS | page_map.csv row count matches content.pdf page count | 666 rows |
| PASS | page_map.csv content_pdf_page is a contiguous 1..N run |  |
| PASS | page_map.csv original_page is strictly increasing, no dup |  |
| PASS | every question's content_page/page_end is inside content.pdf | 750 rows checked |
| PASS | page_end >= content_page for every question |  |
| PASS | original_page / orig_page_end match page_map.csv exactly | tag stage agrees with split stage on every row |
| PASS | no duplicate q_id (re-derived independently) | 750 ids, all unique |
| PASS | every section is a clean 1->N run (re-derived independently) | 30 sections |
| PASS | independent numbers match stage1_gate_report.json |  |
| PASS | shift/paper labels: every section labelled, count matches expected | 10 distinct labels, 30 sections / 3 subjects = 10 expected |
| PASS | no paper label spans a non-contiguous run of sections |  |
| PASS | orphan content pages match gate report (re-derived independently) | 0 orphan pages |
| PASS | pages/ image count matches content.pdf page count | 666 images |
| PASS | removed/ image count matches ad page count | 1 images |
| PASS | no render failures | render_failures.json absent |

## Spot-check list for a human reviewer

**Ad pages removed** (1): [1]

**REVIEW pages kept** (1): [667]

**Random question sample** — open each `image_hint` and confirm subject/q_no/paper actually match what's printed on that original page:

| q_id | subject | q_no | paper | original_page | image_hint |
|---|---|---|---|---|---|
| S16|Physics|Q020 | Physics | 20 | 4th September Shift 2 | 358 | pages/page_0358.png |
| S18|Mathematics|Q006 | Mathematics | 6 | 4th September Shift 2 | 388 | pages/page_0388.png |
| S02|Chemistry|Q017 | Chemistry | 17 | 2nd September 2020 - Shift 1 | 42 | pages/page_0042.png |
| S11|Chemistry|Q016 | Chemistry | 16 | 3rd September Shift 2 | 243 | pages/page_0243.png |
| S21|Mathematics|Q024 | Mathematics | 24 | 5th September Shift 1 | 467 | pages/page_0467.png |
| S20|Chemistry|Q023 | Chemistry | 23 | 5th September Shift 1 | 445 | pages/page_0445.png |

# Verification report — ..\out\2022_july

**Result: PASS** — 18 pass, 0 warn, 0 fail

| Status | Check | Detail |
|---|---|---|
| PASS | all stage artifacts present |  |
| PASS | questions_index.csv column schema matches reference | q_id,section_index,paper,subject_label,q_no,content_page,page_end,original_page,orig_page_end |
| PASS | total pages = kept + ads | 878 = 875 + 3 |
| PASS | page_map.csv row count matches content.pdf page count | 875 rows |
| PASS | page_map.csv content_pdf_page is a contiguous 1..N run |  |
| PASS | page_map.csv original_page is strictly increasing, no dup |  |
| PASS | every question's content_page/page_end is inside content.pdf | 900 rows checked |
| PASS | page_end >= content_page for every question |  |
| PASS | original_page / orig_page_end match page_map.csv exactly | tag stage agrees with split stage on every row |
| PASS | no duplicate q_id (re-derived independently) | 900 ids, all unique |
| PASS | every section is a clean 1->N run (re-derived independently) | 30 sections |
| PASS | independent numbers match stage1_gate_report.json |  |
| PASS | shift/paper labels: every section labelled, count matches expected | 10 distinct labels, 30 sections / 3 subjects = 10 expected |
| PASS | no paper label spans a non-contiguous run of sections |  |
| PASS | orphan content pages match gate report (re-derived independently) | 0 orphan pages |
| PASS | pages/ image count matches content.pdf page count | 875 images |
| PASS | removed/ image count matches ad page count | 3 images |
| PASS | no render failures | render_failures.json absent |

## Spot-check list for a human reviewer

**Ad pages removed** (3): [1, 2, 878]

**REVIEW pages kept** (1): [877]

**Random question sample** — open each `image_hint` and confirm subject/q_no/paper actually match what's printed on that original page:

| q_id | subject | q_no | paper | original_page | image_hint |
|---|---|---|---|---|---|
| S29|Chemistry|Q025 | Chemistry | 25 | 29 July - Evening Shift | 842 | pages/page_0842.png |
| S14|Chemistry|Q005 | Chemistry | 5 | 27 July - Morning Shift | 383 | pages/page_0383.png |
| S26|Chemistry|Q027 | Chemistry | 27 | 29 July - Morning Shift | 759 | pages/page_0759.png |
| S15|Mathematics|Q011 | Mathematics | 11 | 27 July - Morning Shift | 417 | pages/page_0417.png |
| S02|Chemistry|Q012 | Chemistry | 12 | 25 July - Morning Shift | 44 | pages/page_0044.png |
| S09|Mathematics|Q026 | Mathematics | 26 | 26 July - Morning Shift | 256 | pages/page_0256.png |

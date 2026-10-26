# Stage 2 progress log

Distillation data pipeline, Stage 2: take Stage 1's cleaned JEE Mains PDFs
(`jee_mains_even_years_combined_deliverables/`) and turn every question into
one markdown file, using MinerU's vlm-engine for text/LaTeX/tables and
Bedrock (Gemma) for image captions, since MinerU alone was found (on a prior
textbook run) to be weak on images specifically.

This file is a running log, not a spec - append to it, don't rewrite history.

---

## 2026-09-24 - Design walkthrough + scripts built

**Inputs confirmed** (`jee_mains_even_years_combined_deliverables/`, 8 years,
~5,775 questions total): `content.pdf` (ad-free), `questions_index.csv`
(per-question page ranges into content.pdf), `page_map.csv`, `sections.json`,
`profile.json` (question-boundary regex), plus Stage 1's own QA trail
(`stage1_gate_report.json`, `verification_report.*`).

**Core design decision**: run MinerU vlm-engine *once per year* on the whole
`content.pdf` (8 GPU invocations, not ~5,775), then slice its parsed output
into per-question `.md` files using `questions_index.csv`'s page ranges +
`profile.json`'s question-start regex. Consecutive questions' page ranges
overlap by one page (Q1: pages 1-2, Q2: pages 2-3) - turns out this is mostly
because a question's *solution* is delivered as an image that visually
overflows onto the next page (confirmed by inspecting 2018 content.pdf pages
1-3 directly: page 1's extractable text ends right after "Solution:" with no
solution text, page 2's text starts clean at "Q. 2"). Slicing on text
markers rather than raw page boundaries handles this correctly regardless of
which page hosts the image vs. the next question's text - verified against
real page text, see "Verification" below.

**Data-quality finding: missing shift labels.** `sections.json` /
`questions_index.csv` have blank `paper` for 2026_jan (all 750 questions)
and 2026_april (first 75, one shift). Root cause: the table-of-contents /
divider pages that named each shift were correctly flagged as ads and
pulled from `content.pdf` - but they were the only place the label text
lived. Stage 1 archived rather than deleted ad pages though
(`removed_ads.pdf`), so the mapping is recoverable deterministically:
parsed the ToC pages, matched each blank section's `original_page_start`
against the recovered (label, start_page) pairs. Implemented in
`scripts/common/labels.py` / `scripts/00_recover_labels.py`, output goes to
`output/<year>/label_overrides.json` (Stage 1's own files are never
touched). Ran it - all 30/2026_jan sections and 3/2026_april sections
recovered correctly, verified against `removed_ads.pdf` text by hand first.

Also corrected an assumption from the chat: 2024_april *does* have 2 shifts
(5 dates x Morning/Evening = 10 papers, matches its 900 questions) - it's
not an exception like 2018 is (2018 = 1 offline paper + 1 online paper x 2
shifts, 3 papers total, 270 questions).

**GPU/disk requirements captured** (A10 notebook, per user): one long-lived
MinerU process/model load across all years rather than reloading per year;
Bedrock captioning threaded and overlapped with MinerU's GPU work rather
than serialized after it; per-year disk cleanup of MinerU's bulky debug
output once that year's `.md` files validate, keeping only the referenced
image crops + `content_list.json` (so a re-split doesn't require re-running
MinerU) + the final `questions_md/`.

**External-dependency uncertainty, and how it's handled**: MinerU's exact
CLI flags and JSON output schema could not be independently verified from
docs alone (search results were inconsistent across versions - some
describe `mineru -p/-o/-b`, others a different `mineru-kit` CLI surface).
Rather than hardcode a guess, `common/mineru_adapter.py` is defensive: it
tries several candidate output filenames and field-name spellings, and
fails loudly with a clear message if none match, instead of silently
emitting wrong/empty output. `scripts/inspect_mineru_output.py` is a
calibration tool to run first on the AWS box against one real MinerU
output directory. **This calibration is the actual first step of the pilot
run on AWS, not an afterthought.**

Bedrock auth confirmed via web search: `AWS_BEARER_TOKEN_BEDROCK` env var,
boto3's `bedrock-runtime` client picks it up automatically. Whether Gemma
is a native Bedrock model id or a Bedrock Marketplace endpoint ARN is
still unknown (user only has an API key, not sure of the backend) -
`common/bedrock_client.py` just takes `BEDROCK_MODEL_ID` as a single config
value since Bedrock's `Converse` API accepts either in the same parameter.

**Scripts built** (`scripts/`):
- `common/config.py` - all tunables (MinerU backend/device, Bedrock model
  id/concurrency, disk-cleanup toggles, pilot size), env-var overridable.
- `common/io_utils.py`, `common/pdf_utils.py` - Stage 1 file readers,
  PyMuPDF helpers (page image counts, working-PDF subset builder for the
  pilot).
- `common/labels.py` - the label-recovery logic above.
- `common/scope.py` - unifies "run a full year" and "run just the pilot's
  questions for this year" behind one `ScopeYear` interface so every
  downstream script has one code path, not two.
- `common/mineru_adapter.py` - runs the `mineru` CLI, normalizes its output
  into a flat block list.
- `common/bedrock_client.py` - `caption_image()` via Converse API, retries
  on throttling.
- `00_recover_labels.py`, `01_select_pilot.py`, `02_run_mineru.py`,
  `03_caption_images_bedrock.py`, `04_split_questions.py`, `05_validate.py`
  (mirrors Stage 1's `verification_report.md` style), `06_cleanup.py`
  (dry-run by default, `--execute` to actually delete).
- `run_pipeline.py` - orchestrates 00->05(->06) per scope, checkpointed via
  `output/<scope>/<year>/_state.json` so a crash doesn't force a redo.
- `inspect_mineru_output.py` - calibration tool, see above.

**Pilot selection** (`01_select_pilot.py`, ran successfully): 30 questions,
weighted toward 2026_jan (6) and 2026_april (5) to stress-test label
recovery specifically - including a forced pick from 2026_april's actually-
recovered section (1-3, "2nd April 1st Shift") so the pilot proves the fix
landed on the previously-blank section, not just any section of that year.
Balanced 10/10/10 across Physics/Chemistry/Mathematics (first version of the
selector was accidentally ~23/30 Physics - a real bug, fixed: the "guarantee
an image-bearing pick" pass was breaking out of the subject loop on its
first hit instead of rotating, and round-robin was restarting at index 0
after it; rewrote as "always draw from the currently most under-represented
subject"). Output: `output/_pilot/pilot_selection.json`.

**Verification done locally** (no GPU needed for any of this):
- Label recovery re-derived by hand against `removed_ads.pdf` text before
  trusting the script's output.
- Pilot selector's balance/coverage checked by inspection after the fix.
- Built a synthetic MinerU `content_list.json` using **real** extracted text
  from 2018 `content.pdf` pages 1-3 (Q1/Q2/Q3, real overlap case) plus a
  fake image block, and ran the actual `build_markdown`/`_slice_blocks`
  functions from `04_split_questions.py` against it. Confirmed: Q1's slice
  stops exactly before "Q. 2" (no leak into the next question), Q2 starts
  exactly at its own "Q. 2" marker (no leftover from Q1's trailing solution
  text), the image caption is correctly reinjected as a `> Image
  description:` blockquote, frontmatter renders correctly. This is the
  highest-risk hand-written piece of the pipeline and it's now verified
  against real data, not just reasoned about.

**Not yet run / can't be, off the AWS box**: `02_run_mineru.py` (needs GPU +
installed MinerU), `03_caption_images_bedrock.py` (needs a real
`BEDROCK_MODEL_ID` + credentials), and therefore the pilot hasn't actually
produced real output yet - only the selection step has.

---

## 2026-09-24 (cont.) - Accuracy verification pipeline

Structural QA (`05_validate.py`) only checks file counts/non-empty/frontmatter
- it says nothing about whether the extracted *content* is right. Added a
separate accuracy layer:

- `common/slicing.py`: pulled the boundary-slicing algorithm out of
  `04_split_questions.py` so it's shared, not duplicated.
- `common/reference_extract.py`: an independent, MinerU-free re-extraction of
  each question straight from `content.pdf`'s text layer via PyMuPDF, sliced
  with the *same* (already-verified) boundary algorithm. The point isn't
  that this is a better extractor - it loses table/formula structure MinerU
  is good at - it's that if MinerU's output and this independent path
  disagree wildly, that's a real signal something broke, not the pipeline
  checking itself against itself.
- `06_verify_accuracy.py`: scores each question's similarity against that
  independent reference (SequenceMatcher ratio), plus checks: boundary leaks
  (next question's marker present), missing answer/solution marker vs. the
  reference, LaTeX/brace balance, and image-caption sanity (empty,
  placeholder, refusal-shaped, or suspiciously duplicated captions). Also
  renders a human spot-check package (`output/<scope>/<year>/review/`) -
  every flagged question's original page(s) as PNGs plus a random sample of
  clean ones (pilot renders all 30, a full year renders flagged + a sample),
  with a `review.md` table for a human to eyeball page-vs-markdown.
  `07_cleanup.py` (renamed from `06_cleanup.py`) now also refuses to run if
  accuracy verification flagged FAIL for that year.

**Verified the verifier itself**, not just built it: constructed a fake
pipeline output with one correct question and one deliberately corrupted
one (garbled text, a leaked "Q. 3" marker, missing the solution). Ran
`verify_one()` against it - correctly scored the good one 1.0/no flags and
the bad one 0.21 similarity with `boundary_leak`, `low_similarity`, and
`answer_marker_missing_vs_reference` all correctly flagged, overall FAIL.
Also rendered a real page via `pdf_utils.render_pages()` and visually
inspected it (2018 Q1) to confirm the spot-check images are actually
legible.

**Finding from that inspection, and a real fix**: 2018's content.pdf page 1
renders the entire worked solution (every equation) as a baked-in image,
not selectable text - not just occasional diagrams. That means Bedrock's
job isn't only "describe figures", it's often "transcribe a screenshotted
solution faithfully" - describing it instead of transcribing it would
silently lose real solution content from the distillation data. Rewrote
`BEDROCK_IMAGE_PROMPT` in `common/config.py` to handle both cases (describe
figures/diagrams; faithfully transcribe rendered solution text/equations
step by step, don't summarize). Also renamed the caption blockquote label
from "Image description:" to "Image content:" throughout (`04_split_
questions.py`, `05_validate.py`, `06_verify_accuracy.py`) since it may now
hold a full transcription, not a short description - re-verified the
checker still works after the rename.

---

## 2026-09-24 (cont.) - Shrunk the pilot's AWS upload from 533MB to 8MB

Was about to have the user upload the full `jee_mains_even_years_combined_
deliverables/` (533MB, all 8 years' `content.pdf`) to run a 30-question
pilot - unnecessary. `06_verify_accuracy.py`'s reference re-extraction and
page-rendering were the only things still reading the full `content.pdf`
in pilot mode (everything else already worked off the small per-year
working-PDF subset `02_run_mineru.py` builds). Refactored both to read
`sy.working_pdf` instead, via a new `ScopeYear.working_pages_for()` that
translates a content.pdf page range into the working PDF's own page numbers
(identity for a full-year run, a real lookup for the pilot subset) -
`common/reference_extract.py`, `06_verify_accuracy.py`. Also decoupled
`scope.iter_scope()`'s pilot branch from requiring `content.pdf` to exist at
all (it was only ever used as an existence check, never actually read).

Pre-built the pilot's 8 small working PDFs locally (`ensure_working_pdf()`
for each pilot year, ~10MB total vs. 533MB) and packaged a lean upload:
`scripts/`, `requirements.txt`, `progress.md`, `output/_pilot/` (selection +
the 8 working PDFs + pagemaps), and just `profile.json` per pilot year (no
`content.pdf`/`removed_ads.pdf`/CSVs needed for the pilot). **Verified this
package works in total isolation**: extracted it to a location with zero
access to the original deliverables folder, ran `scope.iter_scope("_pilot")`
against it - all 8 years resolved their working PDF, page map, and
`profile.json` correctly, confirmed `has_full_content_pdf=False` everywhere.
Final zip: `Stage2_pilot_package.zip`, 8MB.

The full 533MB deliverables folder is still needed eventually, just not for
the pilot - that's a separate upload before the full 8-year run.

---

## 2026-09-24 (cont.) - On the real AWS box: two architecture surprises

First real session on the actual SageMaker Notebook Instance (`ec2-user@ip-
172-28-122-190`, `/home/ec2-user/SageMaker/`, A10G confirmed via
`nvidia-smi`, Python 3.10.21). Lean pilot package (8MB, see previous entry)
uploaded and extracted cleanly. Two things we built against turned out to
be wrong, both caught before wasting GPU time - exactly why the calibration
step existed.

**1. MinerU's CLI is completely different from what `common/config.py`/
`mineru_adapter.py` assumed.** Installed version is 4.0.7 via `pip install
-U "mineru[core]"`, and `mineru --help` shows a document-library-centric
tool (`parse`, `scan`, `search`, `list`, `server`...) with no `-p/-o/-b/-l`
flags at all - not the open-source `opendatalab/MinerU` vlm-engine CLI I'd
guessed. `mineru parse --help` shows `--pages`, `--output`, `--tier`,
`--remote`, `--force`, `--wait`/`--no-wait` instead.

More importantly, `mineru config show` (after `mineru server start`)
revealed the actual architecture:
```
Local (disabled)  -> parse_server.local.mode: disabled
Remote (healthy)  -> https://mineru.net/api  (parse_server.remote.api_key: EMPTY)
```
By default this installation sends every parse to mineru.net's cloud
service, not the local A10 GPU - and with no API key set. "Local" mode
isn't "run inference in this process on this GPU" either; its config keys
are `self_hosted_url`/`self_hosted_api_key`, meaning it means "point at a
self-hosted MinerU-compatible endpoint you already have running somewhere."
**Open question sent back to the user's team**: is there an internal
self-hosted MinerU endpoint to point `parse_server.local.self_hosted_url`
at, or an mineru.net API key to use, or is the cloud default actually
acceptable for this content? (Also worth them confirming: JEE PDFs here
carry Careers360 branding, i.e. likely licensed content - sending it to a
third-party cloud parser by default is a real question, not just a
technical one.) `common/mineru_adapter.py`'s CLI invocation has NOT been
updated yet - blocked on this answer, since the right fix depends on it
(a config value vs. a different call shape entirely).

**2. Gemma isn't called via boto3 at all - it's "Mantle".** The user's
senior confirmed: most Bedrock models go through native boto3
`bedrock-runtime`, but Gemma 4 31B specifically requires a separate
OpenAI-compatible gateway called "Mantle" (`https://bedrock-mantle.us-
east-1.api.aws/openai/v1`), using the `openai` Python SDK with a custom
`base_url`, same underlying Bedrock API key but passed as `OPENAI_API_KEY`
rather than `AWS_BEARER_TOKEN_BEDROCK`. The team shared their own existing
Gemma client as a reference (`GemmaRequest`/`GemmaResponse`/`Gemma4Client` -
solid production code: retry taxonomy across TRUNCATED_OUTPUT/REPETITION_
LOOP/INVALID_JSON/MALFORMED_EXPRESSION, one-shot corrective retries per
failure type, image payload size budgeting, stateless-request assertions,
`complete_json()` returning parsed structured output).

Rewrote `common/bedrock_client.py` to match this transport (openai SDK,
base64 data-URL images, `chat.completions.create`) instead of the original
boto3 Converse API guess. Kept `caption_image() -> str` returning plain
text for now (matches this pipeline's current blockquote format) rather
than porting the team's full JSON-schema/retry-taxonomy machinery, since
that's a real design decision, not just a transport detail. Added
`GEMMA_BASE_URL`/`GEMMA_API_KEY`/`GEMMA_MODEL_ID` to `common/config.py`.
Added `openai` to `requirements.txt`.

**Open questions sent back to the user, to relay to their senior**:
1. The exact `model_id` string for Gemma 4 31B on the Mantle endpoint (not
   guessable).
2. Plain-text captions (current design) vs. matching the team's existing
   structured-JSON schema - do they have an example output schema, given
   evidence of prior related work (a `10X_gemma_pilot-run` folder exists on
   the user's machine)?
3. The MinerU local-vs-remote resolution above.

(Also: the same Bedrock API key value got pasted into chat twice now.
Declined to write it into any file either time; told the user to rotate it
and only ever export it as an env var directly on the AWS box.)

---

## 2026-09-25 - Full rewrite against MinerU 4.0.7's real output shape

Resolved the MinerU local-vs-remote question ourselves, collaboratively with
the user live on the AWS terminal, without waiting further on the team:

- `mineru-kit models download --tier standard` (~3GB: layout/OCR/table/
  formula ONNX models + a small GGUF VLM) - the local `managed` mode needs
  these and errors clearly telling you so if missing.
- `mineru config set parse_server.local.mode managed` (valid values, learned
  from the CLI's own validation error: `disabled`, `managed`, `self_hosted` -
  "managed" means MinerU runs its own local model, no external endpoint
  needed).
- `mineru telemetry disable` - required for automated/scripted runs, since
  the first `parse` call blocks on an interactive Y/N prompt otherwise and
  would hang forever under a non-interactive subprocess call.
- First real `mineru parse` confirmed **Local (managed) healthy, running on
  PID, real GPU inference logged** (`OCR-det`/`OCR-rec` progress bars,
  `model_list infer finished... speed=2.7-4.6 page/s` after model warm-up).
  Note: onnxruntime logs a GPU-discovery warning (`/sys/class/drm/card0`
  path doesn't exist on a headless cloud GPU) - the small ONNX submodels
  likely fall back to CPU; not chased yet, fine for pilot scale.

**The actual output format turned out to be nothing like what any earlier
guess assumed** - not a directory with content_list.json + images/, not
even structured JSON by default. `mineru parse <pdf> --pages all --output
<path> --tier standard` writes ONE markdown file (`--output` is a file
path, confirmed via `ls -la` showing a regular file, not a directory) with:
- `<!-- page N of M -->` HTML comments marking page boundaries (1-indexed,
  matches input PDF page order).
- Images inline as **locators**, not file paths:
  `![Image block](doc:<short_id>/tier:<tier>/page:<p>/block:<b>)`. No
  images/ folder exists from the parse call itself.
- Confirmed `mineru read "<locator>" --format image --output <path>`
  actually materializes a real PNG (108KB, real file) - this is how image
  assets get fetched, one CLI call per image block.
- Text/LaTeX quality on real output looks good (compared a real rendered
  page against MinerU's transcription of an adjacent question - consistent
  fidelity).

**Rewrote to match, verified against the real captured output before
touching anything downstream** (not just reasoned about):
- `common/mineru_adapter.py`: full rewrite. `run_mineru()` now calls `mineru
  parse ... --tier <tier> --wait <seconds>` correctly. `load_blocks()`
  parses the single markdown file (regex-split on page markers, then on
  inline image locators) into the same ordered block-list shape the rest of
  the pipeline already expected - verified with a hand-built copy of the
  REAL markdown the user pasted from the terminal: correct block count,
  correct page numbers, correct locator extraction. New `image_filename()`/
  `image_relpath()` helpers give one consistent path string used everywhere
  an image is referenced (the saved asset location, the captions.json key,
  and the final markdown's `![](...)` link) so 03/04/06 can't drift out of
  sync. New `fetch_image_asset()` wraps `mineru read --format image`.
- `common/scope.py`: `mineru_output_md` (a file, not `mineru_out_dir` which
  is now just a scratch/log dir) and `images_dir` (a sibling of
  `questions_md/`, deliberately outside `mineru_raw/` so `07_cleanup.py`'s
  debug-output deletion can never touch the actual image assets a
  question's .md depends on).
- `02_run_mineru.py`, `03_caption_images_bedrock.py`, `04_split_questions.py`
  updated to the new adapter interface. `03` now fetches each image asset
  via `fetch_image_asset()` before captioning (there's no pre-existing file
  to read anymore). `04`'s `_block_text_for_render()` uses `image_relpath()`
  for both the caption lookup and the rendered link.
- Removed `MINERU_BACKEND`/`MINERU_LANG`/`MINERU_DEVICE`/
  `MINERU_PAGE_IDX_IS_ZERO_BASED` from `common/config.py` (none apply to
  this CLI) - added `MINERU_TIER`/`MINERU_WAIT_SECONDS`/`MINERU_FORCE_REPARSE`.

**End-to-end verification**: built a synthetic `content_list`-equivalent
from the REAL markdown text the user pasted from their terminal (2018,
Q.9/Q.10/Q.24 with a real image locator), ran it through
`mineru_adapter.load_blocks()` -> the boundary slicer -> `04_split_
questions.py`'s actual `build_markdown()`. Result: Q.9's slice starts
exactly at its own marker (excludes the previous question's trailing
fragment), stops exactly before "Q. 10" (excludes the next question), the
image lands in the correct position with its caption correctly reinjected
as a blockquote, frontmatter renders correctly. This is the same slicing
algorithm verified earlier against synthetic data, now re-verified against
the real MinerU 4.0.7 output shape end to end.

**Gemma/Mantle**: model id confirmed by the team - `google.gemma-4-31b`.
Plain-text `.md` output (not JSON) confirmed as the right call - matches
what was already built, no schema change needed.

**Still open**: the licensing/compliance question (is mineru.net's cloud
default actually a concern here, now moot for THIS box since local managed
mode works - but worth the team knowing local was silently defaulting to an
unconfigured remote cloud call before we fixed it, for when other people
set up their own instances).

---

## 2026-09-25 (cont.) - First real pilot run, two bugs found and fixed by eye

`run_pipeline.py --pilot` actually executed end to end for the first time.
MinerU parsing and splitting worked cleanly on the first try (all 8 years,
correct question counts). Two real bugs surfaced downstream, both caught by
actually looking at output rather than trusting summary stats:

**Bug 1 - stale scripts on the AWS box.** First `run_pipeline.py --pilot`
crashed inside `mineru_adapter.run_mineru()` calling the OLD 3-arg
directory-based signature - the AWS box was still running the very first
zip upload; none of the MinerU-4.0.7 rewrite or the Mantle/Gemma client
rewrite had been synced there. No code fix - repackaged just `scripts/`
(35KB) as a separate small zip for re-upload, since the working PDFs/
pilot_selection.json in the original upload hadn't changed. Lesson: when
editing local files against a running remote session, the remote needs an
explicit re-sync step - it doesn't happen automatically. Should package a
fresh scripts-only zip after every further edit, going forward.

**Bug 2 - `OPENAI_API_KEY` not actually set.** All 39 image captions failed
with a clean, correctly-surfaced error (`OPENAI_API_KEY is not set...`) -
turned out the user had pasted an *example command with a placeholder*
literally into the terminal instead of substituting their real key. Once
corrected, all 39/39 captions succeeded on the real Mantle/Gemma endpoint -
first real end-to-end confirmation that `common/bedrock_client.py`'s OpenAI-
SDK rewrite actually works against the real service, not just our own
send/receive analysis of the reference client.

**Bug 3 - the real one, in our own accuracy checker.** After captions
succeeded, `06_verify_accuracy.py` still flagged the large majority of
pilot questions FAIL/WARN on `low_similarity`/`marginal_similarity`
(scores from 0.07 to 0.83, no consistent pattern). Rather than trust the
automated flag, walked the user through the actual human spot-check
package (`review.md`) for the worst case (`S04|Physics|Q009`, similarity
0.227) - **the `.md` content was completely correct**: right question,
right options, right answer, right solution steps, and a genuinely good,
detailed multi-paragraph image caption (geometry, labeled points, angles,
shading - all accurate against the rendered page). So the pipeline output
was fine; the checker was wrong. Root cause found by inspecting that exact
caption: `_pipeline_body()`'s regex for stripping `> Image content: ...`
blocks before computing similarity only matched up to the *first* blank
line, so it only stripped the first paragraph of a caption - multi-
paragraph structured captions (which the corrected image prompt, see
earlier entry, now routinely produces) leaked the rest into the text being
compared against the image-blind PyMuPDF reference, dragging the score down
specifically on the questions where Gemma did the most thorough job.

Fixed properly rather than patching the regex: added `common/mineru_
adapter.blocks_by_content_page()` (shared by `04_split_questions.py` and
`06_verify_accuracy.py`, removing some duplicated block-loading logic from
04 too) and a new `_pipeline_text_only()` in `06_verify_accuracy.py` that
slices MinerU's own blocks (same boundary algorithm, same as `04` and
`reference_extract`) and joins only `type == "text"` blocks - image
captions are structurally excluded from the comparison rather than
regex-stripped after the fact. Verified: rebuilt the real Q.9 case as a
block list, confirmed `"Geometry" not in pipeline_text` (caption fully
excluded) and similarity against a rough plain-text reference jumped from
the old 0.227 (false positive) to 0.615 - the residual gap being the
expected/legitimate difference between MinerU's clean LaTeX and a
non-LaTeX comparison baseline, not a defect.

**Bug 4 (minor, cosmetic but real) - markdown table breakage.** `q_id`
values look like `S04|Physics|Q009` - embedding them directly into a
markdown table row means their own `|` characters get parsed as extra
column separators, shifting every subsequent column and dropping the
page-image/`.md` link columns entirely from `review.md`. Fixed in both
`build_review_package()` and `render_summary()` by displaying the
sanitized/underscored form instead (`io_utils.sanitize_q_id()`, already
computed elsewhere for filenames).

Net effect: the pipeline's actual output was good this whole time: the
FAIL/WARN results were coming from our own verification tooling, not from
MinerU or Gemma. This is exactly the failure mode the human spot-check
package exists to catch - relying on the automated similarity score alone
would have wrongly suggested a content problem.

---

## 2026-09-25 (cont.) - Last-question-of-section boundary leak, found and fixed

After the caption-exclusion fix, most similarity scores landed in a
plausible 0.4-0.9 range, but `S21|Mathematics|Q030` (2022_july, in the
pilot) stayed flagged with `boundary_leak(other_q_no_present=[1])`.
Verified against real data before assuming it was another checker bug:
`sections.json` confirms section 21 (Mathematics, 28 July Morning Shift)
has exactly 30 questions ending at content page 607, and section 22
(Physics, Evening Shift) *starts* at page 607 - same page. Root cause:
numbering resets per section (confirmed in every year's profile.json), so
the last question in a section has no "q_no + 1" to search for as an end
boundary - the slicer fell back to "take the rest of the page range",
which included the next section's own "Q. 1" header. Not pilot-specific:
this hits roughly one question per section across the full 8-year corpus
(~240+ questions in the full run, not just this one pilot case).

Fixed at the source (`common/slicing.py`'s new `find_end_marker()`): if
"q_no + 1" isn't found AND the question is the last in its section, fall
back to searching for the next section's own "Q. 1" instead of taking
everything remaining. Needed knowing "is this the last question in its
section" reliably in both the full-year AND pilot scopes - for the pilot,
`sy.rows` is only a small sample and can't be used to infer a section's
true last question, so this is now computed once in
`io_utils.read_questions_index()` from `sections.json`'s `n_questions`
(authoritative regardless of what subset ends up sampled) and flows through
`pilot_selection.json` automatically. Wired into all three slicing call
sites: `04_split_questions.py`, `06_verify_accuracy.py`'s
`_pipeline_text_only()`, and `common/reference_extract.py`.

Verified against the real 2022_july `content.pdf` (not just reasoned
about): `S21|Mathematics|Q030`'s reference slice now ends cleanly at "...
Correct Answer: No real values possible Solution: 608 Physics" - the
question's own content is complete and correct, and the leaked next-
question CONTENT is gone. (Minor residual: a stray page number and the
next section's subject-label word still trail in - page furniture, not
duplicated question content; not chasing further for now.)

Regenerated `pilot_selection.json` locally (same seed -> identical 30
questions, now carrying `is_last_in_section` per row) - no need to rebuild
the working PDFs on AWS, only the split/accuracy logic and this one JSON
file changed.

### Next steps (on the AWS A10 notebook)

Environment is now actually set up correctly (all done live on the box,
2026-09-24/25): `mineru[core]` 4.0.7 installed, local `managed` GPU parsing
enabled and confirmed healthy, `openai` installed, `GEMMA_MODEL_ID`/
`OPENAI_BASE_URL`/`OPENAI_API_KEY` exported. `common/mineru_adapter.py` and
`common/bedrock_client.py` are rewritten and verified against real captured
output (not the original guesses). We were mid-way through manual
`mineru parse`/`mineru read` calls to calibrate, rather than having run our
own scripts yet.

1. Delete the manual test artifacts from calibration if still present:
   `output/_pilot/2018/mineru_raw/test_parse`, `test_block.png`.
2. `python scripts/run_pipeline.py --pilot` - this is the first real
   end-to-end run of our own scripts against the corrected adapter. Expect
   the first `mineru parse` call per year to be slower (model warm-up
   observed ~55s cold vs. ~1.5-2.5s warm per 7-page batch); the pipeline
   processes years sequentially so only the very first call pays that cost.
3. Check results in order of how much they actually tell you:
   - `output/_pilot/*/accuracy_report.md` - per-question similarity scores
     and flags (boundary leaks, missing answers, bad captions).
   - `output/_pilot/*/review/review.md` - every one of the 30 pilot
     questions has its original page(s) rendered as PNG right next to its
     `.md`. Compare a handful by eye, especially 2026_jan/2026_april (label
     recovery) and the image-heavy ones (Gemma transcription/description
     quality - note the prompt now asks it to transcribe rendered-solution
     images faithfully, not just describe figures, since that's what most
     of this corpus's images turned out to be).
   - `output/_pilot/*/qa_report.md` - structural sanity, lowest signal.
4. Once the pilot looks right: upload the full ~533MB
   `jee_mains_even_years_combined_deliverables/` (not needed for the pilot,
   is needed for the full run), then `python scripts/run_pipeline.py --all
   --cleanup`.

Open items to close out with the team when convenient (not blocking): the
mineru.net cloud-by-default / licensed-content question (moot for this box
now that local `managed` mode works, but worth others knowing about before
they spin up their own instance), and whether the onnxruntime GPU-discovery
warning (small ONNX submodels possibly falling back to CPU) is worth chasing
once we're past pilot scale.

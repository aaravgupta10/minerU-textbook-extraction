"""
Central config for the Stage 2 pipeline. Everything that might differ between
this laptop (no GPU, used for label recovery / pilot selection / dry runs)
and the AWS A10 notebook (real MinerU + Bedrock runs) lives here as an
env-var-overridable constant, not scattered through the scripts.
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DELIVERABLES_DIR = PROJECT_ROOT / "jee_mains_even_years_combined_deliverables"
OUTPUT_DIR = PROJECT_ROOT / "output"
PILOT_SCOPE = "_pilot"


def year_dirs():
    """All Stage 1 year folders that actually contain a content.pdf."""
    if not DELIVERABLES_DIR.exists():
        return []
    return sorted(
        p for p in DELIVERABLES_DIR.iterdir()
        if p.is_dir() and (p / "content.pdf").exists()
    )


def scope_output_dir(scope: str) -> Path:
    """output/<year>/ for a real run, output/_pilot/<year>/ for the pilot."""
    return OUTPUT_DIR / scope


# ---------------------------------------------------------------------------
# MinerU (runs only on the GPU box). Calibrated against the real installed
# CLI (version 4.0.7) on 2026-09-24/25 - see progress.md "On the real AWS
# box" entries. This is a document-library product, not the old
# opendatalab/MinerU vlm-engine CLI originally guessed here: `mineru parse
# <pdf> --pages all --output <path> --tier <tier>` writes a single markdown
# file (not a directory), and local GPU parsing must be explicitly enabled
# once per machine with:
#   mineru-kit models download --tier standard
#   mineru config set parse_server.local.mode managed
# (as opposed to the default, which silently sends PDFs to mineru.net's
# public cloud service - a real problem for licensed exam content, and it
# has no API key configured anyway). See common/mineru_adapter.py.
# ---------------------------------------------------------------------------
MINERU_CLI = os.environ.get("MINERU_CLI", "mineru")
MINERU_TIER = os.environ.get("MINERU_TIER", "standard")
MINERU_TIMEOUT_SEC = int(os.environ.get("MINERU_TIMEOUT_SEC", str(6 * 3600)))
MINERU_WAIT_SECONDS = int(os.environ.get("MINERU_WAIT_SECONDS", str(3600)))
MINERU_FORCE_REPARSE = os.environ.get("MINERU_FORCE_REPARSE", "0") == "1"

# ---------------------------------------------------------------------------
# Gemma, via "Mantle" - an OpenAI-compatible gateway in front of Bedrock,
# confirmed by the team: most Bedrock models go through native boto3
# bedrock-runtime, but Gemma specifically is only reachable through this
# OpenAI-compatible endpoint (openai Python SDK, custom base_url). Same
# underlying Bedrock API key either way, just used as OPENAI_API_KEY here
# instead of AWS_BEARER_TOKEN_BEDROCK. Nothing here should ever hold the key
# itself - it's read from the environment at runtime only.
# ---------------------------------------------------------------------------
BEDROCK_REGION = os.environ.get("AWS_REGION", "us-east-1")
GEMMA_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://bedrock-mantle.us-east-1.api.aws/openai/v1")
GEMMA_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMMA_MODEL_ID = os.environ.get("GEMMA_MODEL_ID", "")  # confirm exact string with the team
BEDROCK_MAX_WORKERS = int(os.environ.get("BEDROCK_MAX_WORKERS", "8"))
BEDROCK_MAX_RETRIES = int(os.environ.get("BEDROCK_MAX_RETRIES", "5"))
GEMMA_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("GEMMA_REQUEST_TIMEOUT_SECONDS", "120"))
GEMMA_MAX_OUTPUT_TOKENS = int(os.environ.get("GEMMA_MAX_OUTPUT_TOKENS", "4096"))
BEDROCK_IMAGE_PROMPT = os.environ.get("BEDROCK_IMAGE_PROMPT", (
    "This image was extracted from a JEE Main (Indian engineering entrance "
    "exam) Physics, Chemistry, or Mathematics question or solution. It is one "
    "of two things - handle whichever it actually is:\n"
    "1. A figure/diagram/graph/circuit/chemical structure: describe it "
    "precisely and completely enough for a text-only reasoning model to "
    "answer the question without ever seeing the image - all labeled points, "
    "numeric values, units, axes and scales, geometric relationships, circuit "
    "elements and connections, or structures, as applicable.\n"
    "2. A rendered block of solution text/equations (this corpus often bakes "
    "the entire worked solution into a screenshot image rather than "
    "selectable text): transcribe it FAITHFULLY, step by step, in LaTeX/plain "
    "text, preserving every equation, intermediate step, and the final "
    "answer exactly as shown. Do not summarize or skip steps - this will be "
    "used as training data, so an incomplete transcription silently loses "
    "real content.\n"
    "In both cases: do not add commentary, opinions, or your own solving. "
    "Prefer a structured, literal output over prose."
))

# ---------------------------------------------------------------------------
# Disk hygiene on the GPU box: MinerU's raw per-page debug output is bulky
# (full-page renders, middle.json, layout previews). Once a year's questions
# validate cleanly, everything except the final questions_md/ and the image
# crops actually referenced from it can be discarded.
# ---------------------------------------------------------------------------
CLEANUP_AFTER_VALIDATE = os.environ.get("CLEANUP_INTERMEDIATE", "1") == "1"
KEEP_MINERU_RAW = os.environ.get("KEEP_MINERU_RAW", "0") == "1"

# ---------------------------------------------------------------------------
# Pilot
# ---------------------------------------------------------------------------
PILOT_QUESTION_COUNT = int(os.environ.get("PILOT_QUESTION_COUNT", "30"))
PILOT_SEED = int(os.environ.get("PILOT_SEED", "42"))

# ---------------------------------------------------------------------------
# Accuracy verification (07_verify_accuracy.py). The similarity score is a
# SequenceMatcher ratio between the pipeline's output and an independent
# PyMuPDF-only re-extraction of the same question boundary - see
# common/reference_extract.py for why this is a meaningful cross-check and
# not just the pipeline validating itself against itself.
# ---------------------------------------------------------------------------
ACCURACY_SIMILARITY_FAIL = float(os.environ.get("ACCURACY_SIMILARITY_FAIL", "0.4"))
ACCURACY_SIMILARITY_WARN = float(os.environ.get("ACCURACY_SIMILARITY_WARN", "0.65"))
# How many *additional* (non-flagged) questions to render into the human
# spot-check package for a full-year run. The pilot scope always renders
# every question - it's small on purpose.
ACCURACY_RANDOM_SAMPLE_SIZE = int(os.environ.get("ACCURACY_RANDOM_SAMPLE_SIZE", "15"))
ACCURACY_RENDER_DPI = int(os.environ.get("ACCURACY_RENDER_DPI", "150"))

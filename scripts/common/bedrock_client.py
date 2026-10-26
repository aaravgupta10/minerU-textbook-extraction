"""
Calls Gemma through "Mantle" - an OpenAI-compatible gateway in front of
Bedrock (confirmed by the team; most Bedrock models go through native boto3
bedrock-runtime, Gemma specifically needs this OpenAI-compatible path
instead). Uses the `openai` Python SDK pointed at a custom base_url, images
sent as base64 data URLs - matching the team's own reference Gemma client,
not the boto3 Converse API this module originally guessed.

Auth: OPENAI_API_KEY env var (same underlying Bedrock API key, just used via
this protocol). Never hold the key itself here - read from the environment
only, at call time.

Currently returns a plain caption/transcription string, matching this
pipeline's markdown blockquote format (see 04_split_questions.py). The
team's own reference client returns structured JSON instead
(`complete_json()` style) - switch to that here if Stage 2's output should
match their existing schema; ask before doing that, it changes what
04_split_questions.py embeds in each question's .md.
"""
import base64
import random
import time

from openai import OpenAI

from . import config

_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.GEMMA_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. This is the Bedrock API key, used via the "
                "Mantle OpenAI-compatible gateway rather than native boto3 bedrock-runtime."
            )
        _client = OpenAI(
            api_key=config.GEMMA_API_KEY,
            base_url=config.GEMMA_BASE_URL,
            timeout=config.GEMMA_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,  # retry/backoff handled below, not doubled up in the SDK
        )
    return _client


def _data_url(image_bytes: bytes, image_format: str) -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/{image_format};base64,{b64}"


def caption_image(image_bytes: bytes, image_format: str = "png", prompt: str | None = None) -> str:
    if not config.GEMMA_MODEL_ID:
        raise RuntimeError(
            "GEMMA_MODEL_ID is not set - the exact model id string for Gemma on the "
            "Mantle endpoint, confirm with the team rather than guessing."
        )
    prompt = prompt or config.BEDROCK_IMAGE_PROMPT
    client = get_client()
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": _data_url(image_bytes, image_format)}},
        ],
    }]

    backoff = 1.0
    last_err = None
    for attempt in range(config.BEDROCK_MAX_RETRIES):
        try:
            completion = client.chat.completions.create(
                model=config.GEMMA_MODEL_ID,
                messages=messages,
                max_tokens=config.GEMMA_MAX_OUTPUT_TOKENS,
            )
            text = completion.choices[0].message.content or ""
            return text.strip()
        except Exception as e:  # noqa: BLE001 - classified below, never swallowed
            last_err = e
            status_code = getattr(e, "status_code", None)
            lowered = str(e).lower()
            transient = (status_code in _RETRYABLE_STATUS
                         or "timeout" in lowered or "timed out" in lowered
                         or "connection" in lowered or "throttl" in lowered
                         or "rate limit" in lowered)
            if transient and attempt < config.BEDROCK_MAX_RETRIES - 1:
                time.sleep(min(backoff + random.random(), 30))
                backoff *= 2
                continue
            raise RuntimeError(f"Gemma caption failed via Mantle: {e}") from e
    raise RuntimeError(f"Gemma caption failed after {config.BEDROCK_MAX_RETRIES} attempts: {last_err}")

#!/usr/bin/env python
"""
Finds every image-type block MinerU produced for a scope, materializes each
one as a real PNG via `mineru read <locator> --format image` (there is no
images/ folder from the parse call itself - see common/mineru_adapter.py),
and captions it via Gemma/Mantle, threaded since captioning is network-
bound, not GPU-bound - can run concurrently with the next year's MinerU
pass. No GPU needed for this step itself, but it does still shell out to
the local `mineru` CLI to fetch each image asset.

Usage:
    python scripts/03_caption_images_bedrock.py --pilot
    python scripts/03_caption_images_bedrock.py --year 2026_jan
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import bedrock_client, config, mineru_adapter, scope  # noqa: E402


def run_one(sy: scope.ScopeYear, force: bool):
    state = scope.load_state(sy)
    if state.get("captions_done") and not force:
        print(f"[{sy.scope}/{sy.year_name}] captions already done, skipping (--force to redo)")
        return
    if not state.get("mineru_done"):
        print(f"[{sy.scope}/{sy.year_name}] SKIP: mineru hasn't run yet")
        return

    blocks = mineru_adapter.load_blocks(sy.mineru_output_md)
    image_blocks = [b for b in blocks if b["type"] == "image" and b["locator"]]
    print(f"[{sy.scope}/{sy.year_name}] {len(image_blocks)} image block(s) to caption")

    captions: dict[str, str | None] = {}
    failures: list[str] = []

    def caption_one(locator: str):
        key = mineru_adapter.image_relpath(locator)
        asset_path = sy.images_dir / mineru_adapter.image_filename(locator)
        image_bytes = mineru_adapter.fetch_image_asset(locator, asset_path)
        return key, bedrock_client.caption_image(image_bytes, "png")

    with ThreadPoolExecutor(max_workers=config.BEDROCK_MAX_WORKERS) as pool:
        seen_locators = {b["locator"] for b in image_blocks}
        futures = {pool.submit(caption_one, locator): locator for locator in seen_locators}
        for fut in as_completed(futures):
            locator = futures[fut]
            key = mineru_adapter.image_relpath(locator)
            try:
                _, caption = fut.result()
                captions[key] = caption
            except Exception as e:  # noqa: BLE001 - keep going, report at the end
                captions[key] = None
                failures.append(f"{key}: {e}")

    sy.captions_dir.mkdir(parents=True, exist_ok=True)
    json.dump(captions, open(sy.captions_dir / "captions.json", "w", encoding="utf-8"), indent=2)
    if failures:
        json.dump(failures, open(sy.captions_dir / "failures.json", "w", encoding="utf-8"), indent=2)
        print(f"[{sy.scope}/{sy.year_name}] WARNING: {len(failures)} caption(s) failed "
              f"(see {sy.captions_dir / 'failures.json'})")

    scope.save_state(sy, captions_done=True, n_images=len(image_blocks), n_caption_failures=len(failures))
    print(f"[{sy.scope}/{sy.year_name}] captioned {len(captions) - len(failures)}/{len(image_blocks)}")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true")
    g.add_argument("--year")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    scopes = [config.PILOT_SCOPE] if args.pilot else (
        [y.name for y in config.year_dirs()] if args.all else [args.year]
    )
    for s in scopes:
        for sy in scope.iter_scope(s):
            run_one(sy, args.force)


if __name__ == "__main__":
    main()

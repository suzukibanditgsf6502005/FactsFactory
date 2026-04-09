#!/usr/bin/env python3
"""
scene_image_generator.py — FactsFactory scene image generator

Generates one still image per scene from storyboard image prompts.

Primary provider:  fal.ai (Flux) — fast, cheap (~$0.003–0.008/image)
Fallback provider: OpenAI (DALL-E 3) — if fal fails or FAL_API_KEY missing

Usage:
  # Generate all scenes for a storyboard
  python scripts/production/scene_image_generator.py --storyboard logs/storyboards/TIMESTAMP_slug.json

  # Generate only specific scenes (for testing — 0-indexed)
  python scripts/production/scene_image_generator.py --storyboard logs/storyboards/... --scenes 0,1,2

  # Override provider
  python scripts/production/scene_image_generator.py --storyboard logs/storyboards/... --provider openai

  # Custom video id
  python scripts/production/scene_image_generator.py --storyboard logs/storyboards/... --video-id my-test-001

  # Dry run — print prompts without generating
  python scripts/production/scene_image_generator.py --storyboard logs/storyboards/... --dry-run

Output:
  inbox/{video_id}/scenes/scene_000.png
  inbox/{video_id}/scenes/scene_001.png
  ...
  inbox/{video_id}/scenes/manifest.json
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Provider constants ───────────────────────────────────────────────────────

FAL_MODEL = "fal-ai/flux/dev"          # ~$0.003–0.008/image
OPENAI_MODEL = "dall-e-3"              # ~$0.040/image (standard quality)

# Portrait 9:16 — matches Shorts format
FAL_IMAGE_SIZE = "portrait_16_9"        # 576×1024 from fal.ai
OPENAI_IMAGE_SIZE = "1024x1792"         # Closest 9:16-ish from OpenAI



# ── Prompt builder ───────────────────────────────────────────────────────────

def _build_scene_prompt(scene: dict) -> str:
    """
    Build the final image generation prompt for a scene.

    If the scene has structured infographic fields (main_subject, supporting_elements,
    layout_hint), composes a dense infographic/comic-style educational prompt from them.

    Falls back to scene["image_prompt"] for older storyboard files that lack those fields.
    Short labels only — long text in generated images is unreliable.
    """
    main_subject = scene.get("main_subject")
    supporting = scene.get("supporting_elements")
    layout = scene.get("layout_hint")

    if not (main_subject and supporting and layout):
        # Backward compat: older storyboard JSON without structured fields
        return scene["image_prompt"]

    labels = scene.get("labels_and_callouts") or []
    layout_display = layout.replace("_", " ")
    supporting_str = "; ".join(str(e) for e in supporting[:4])

    prompt = (
        f"Infographic comic-style educational scene, {layout_display} layout, portrait 9:16. "
        f"Main subject: {main_subject}. "
        f"Supporting elements in the same frame: {supporting_str}. "
    )
    if labels:
        # Keep labels short — long text renders poorly in AI image generation
        short_labels = [str(l)[:20] for l in labels[:4]]
        prompt += f"Short text labels/callouts: {', '.join(short_labels)}. "

    prompt += (
        "Style: flat illustration educational infographic, bold outlines, vibrant colors, "
        "multiple visual elements in one composition, arrows pointing between elements, "
        "callout boxes, labeled areas, diagrammatic overlays, high visual density, "
        "clean readable composition. No watermarks, no photorealism, no empty negative space."
    )
    return prompt


# ── Utility ──────────────────────────────────────────────────────────────────

def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return json.loads(raw)


def _make_video_id(topic: str) -> str:
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = topic[:30].lower().replace(" ", "-").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    return f"{date_str}_{slug}"


def _download_image(url: str, dest: Path, retries: int = 3) -> None:
    for attempt in range(retries):
        try:
            urllib.request.urlretrieve(url, dest)
            return
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                raise RuntimeError(f"Failed to download image after {retries} attempts: {e}")


def _write_manifest(scenes_dir: Path, manifest: list, storyboard: dict, video_id: str) -> None:
    manifest_path = scenes_dir / "manifest.json"
    data = {
        "video_id": video_id,
        "topic": storyboard["topic"],
        "total_scenes": storyboard["total_scenes"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenes": manifest,
    }
    manifest_path.write_text(json.dumps(data, indent=2))
    return manifest_path


# ── fal.ai provider ──────────────────────────────────────────────────────────

def _generate_fal(prompt: str, scene_index: int) -> str:
    """Generate image via fal.ai Flux. Returns image URL."""
    import fal_client

    fal_key = os.getenv("FAL_API_KEY", "")
    if not fal_key:
        raise RuntimeError("FAL_API_KEY not set")

    os.environ["FAL_KEY"] = fal_key

    print(f"    [fal.ai] Generating scene {scene_index}...", flush=True)

    result = fal_client.run(
        FAL_MODEL,
        arguments={
            "prompt": prompt,
            "image_size": FAL_IMAGE_SIZE,
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
            "num_images": 1,
            "enable_safety_checker": True,
        },
    )

    images = result.get("images", [])
    if not images:
        raise RuntimeError(f"fal.ai returned no images for scene {scene_index}")

    return images[0]["url"]


# ── OpenAI provider ──────────────────────────────────────────────────────────

def _generate_openai(prompt: str, scene_index: int) -> str:
    """Generate image via OpenAI DALL-E 3. Returns image URL."""
    from openai import OpenAI

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    client = OpenAI(api_key=openai_key)

    print(f"    [openai] Generating scene {scene_index}...", flush=True)

    response = client.images.generate(
        model=OPENAI_MODEL,
        prompt=prompt,
        size=OPENAI_IMAGE_SIZE,
        quality="standard",
        n=1,
    )

    url = response.data[0].url
    if not url:
        raise RuntimeError(f"OpenAI returned no image URL for scene {scene_index}")

    return url


# ── Main generation logic ─────────────────────────────────────────────────────

def generate_scene_images(
    storyboard: dict,
    video_id: str,
    provider: str = "auto",
    scene_indices: list[int] | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Generate images for scenes in the storyboard.

    provider: "fal" | "openai" | "auto" (tries fal first, falls back to openai)
    scene_indices: list of 0-based scene indices to generate; None = all scenes
    dry_run: print prompts without generating or saving

    Returns manifest dict.
    """
    scenes_dir = Path(f"inbox/{video_id}/scenes")
    scenes_dir.mkdir(parents=True, exist_ok=True)

    scenes = storyboard["scenes"]
    if scene_indices is not None:
        scenes = [s for s in scenes if s["scene_index"] in set(scene_indices)]

    # Resolve effective provider
    if provider == "auto":
        provider_env = os.getenv("IMAGE_PROVIDER", "fal").lower()
        fallback_env = os.getenv("IMAGE_FALLBACK_PROVIDER", "openai").lower()
    else:
        provider_env = provider.lower()
        fallback_env = "openai" if provider_env == "fal" else "fal"

    print(f"[scene_image_generator] video_id: {video_id}", flush=True)
    print(f"[scene_image_generator] provider: {provider_env} (fallback: {fallback_env})", flush=True)
    print(f"[scene_image_generator] scenes to generate: {len(scenes)}", flush=True)

    manifest = []

    for scene in scenes:
        idx = scene["scene_index"]
        prompt = _build_scene_prompt(scene)
        dest = scenes_dir / f"scene_{idx:03d}.png"

        if dry_run:
            print(f"\n  [DRY RUN] Scene {idx}:")
            print(f"    prompt: {prompt[:120]}...")
            print(f"    would save to: {dest}")
            manifest.append({
                "scene_index": idx,
                "file": str(dest),
                "provider": provider_env,
                "prompt_preview": prompt[:80],
                "status": "dry_run",
            })
            continue

        # Try primary provider, fall back on error
        image_url = None
        used_provider = None
        last_error = None

        for prov in [provider_env, fallback_env]:
            try:
                if prov == "fal":
                    image_url = _generate_fal(prompt, idx)
                elif prov == "openai":
                    image_url = _generate_openai(prompt, idx)
                else:
                    raise RuntimeError(f"Unknown provider: {prov}")
                used_provider = prov
                break
            except Exception as e:
                last_error = e
                print(f"    [{prov}] ERROR: {e} — trying fallback", flush=True)

        if image_url is None:
            print(f"    FAILED scene {idx}: {last_error}", file=sys.stderr)
            manifest.append({
                "scene_index": idx,
                "file": None,
                "provider": None,
                "status": "failed",
                "error": str(last_error),
            })
            continue

        # Download image
        try:
            _download_image(image_url, dest)
            file_size = dest.stat().st_size
            print(f"    [scene {idx}] Saved: {dest} ({file_size // 1024}KB) via {used_provider}", flush=True)
            manifest.append({
                "scene_index": idx,
                "file": str(dest),
                "provider": used_provider,
                "prompt_preview": prompt[:80],
                "status": "ok",
                "file_size_kb": file_size // 1024,
            })
        except Exception as e:
            print(f"    DOWNLOAD FAILED scene {idx}: {e}", file=sys.stderr)
            manifest.append({
                "scene_index": idx,
                "file": None,
                "provider": used_provider,
                "status": "download_failed",
                "error": str(e),
            })

    # Write manifest
    if not dry_run:
        manifest_path = scenes_dir / "manifest.json"
        manifest_data = {
            "video_id": video_id,
            "topic": storyboard["topic"],
            "total_scenes": storyboard["total_scenes"],
            "generated_scenes": len(scenes),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider_env,
            "scenes": manifest,
        }
        manifest_path.write_text(json.dumps(manifest_data, indent=2))
        print(f"\n[scene_image_generator] Manifest: {manifest_path}", flush=True)

    ok = sum(1 for s in manifest if s["status"] == "ok")
    failed = sum(1 for s in manifest if s["status"] == "failed")
    print(f"[scene_image_generator] Done: {ok} ok, {failed} failed", flush=True)
    return manifest


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate scene images from storyboard")
    parser.add_argument("--storyboard", required=True,
                        help="Path to storyboard JSON from storyboard_generator.py")
    parser.add_argument("--video-id",
                        help="Video ID for output directory (default: auto from topic+timestamp)")
    parser.add_argument("--scenes",
                        help="Comma-separated scene indices to generate, e.g. 0,1,2 (default: all)")
    parser.add_argument("--provider", choices=["fal", "openai", "auto"], default="auto",
                        help="Image provider (default: auto — reads IMAGE_PROVIDER from .env)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print prompts without generating images")
    args = parser.parse_args()

    storyboard_path = Path(args.storyboard)
    if not storyboard_path.exists():
        print(f"ERROR: storyboard file not found: {storyboard_path}", file=sys.stderr)
        sys.exit(1)

    storyboard = json.loads(storyboard_path.read_text())

    video_id = args.video_id or _make_video_id(storyboard["topic"])

    scene_indices = None
    if args.scenes:
        try:
            scene_indices = [int(x.strip()) for x in args.scenes.split(",")]
        except ValueError:
            print("ERROR: --scenes must be comma-separated integers, e.g. 0,1,2", file=sys.stderr)
            sys.exit(1)

    generate_scene_images(
        storyboard=storyboard,
        video_id=video_id,
        provider=args.provider,
        scene_indices=scene_indices,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

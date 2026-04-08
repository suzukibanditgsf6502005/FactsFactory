# Tools & APIs

> All external services used by FactsFactory — keys, costs, how to test.
> Last updated: 2026-04-09

---

## Anthropic (Claude)

**Used for:** Topic selection, fact research, script generation, storyboard, caption analysis, QC.

**Get key:** [console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key

**Models in use:**

| Model | Used in | Approx cost/short |
|---|---|---|
| `claude-haiku-4-5-20251001` | topic_selector, storyboard_generator, ass_captions | ~$0.0005 |
| `claude-sonnet-4-6` | fact_research, script_generator, quality_check | ~$0.005 |

**Test:**
```bash
source venv/bin/activate
python -c "import anthropic; c = anthropic.Anthropic(); print(c.models.list())"
```

**.env key:** `ANTHROPIC_API_KEY`

---

## ElevenLabs

**Used for:** TTS voiceover — voice Lily (`pFZP5JQG7iQjIQuC4Bku`), model `eleven_multilingual_v2`.

**Get key:** [elevenlabs.io](https://elevenlabs.io) → Profile → API Key

**Cost:** ~$0.0003/character → ~$0.03/short (100-word script ≈ 600 chars)

**Test:**
```bash
source venv/bin/activate
python scripts/production/voiceover.py --test
```

**.env keys:** `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`

---

## fal.ai (Flux)

**Used for:** AI image generation — Flux Dev model, portrait_16_9 (576×1024).

**Get key:** [fal.ai](https://fal.ai) → Dashboard → API Keys

**Cost:** ~$0.003–0.008/image → ~$0.024–0.064/short (8 images)

**Test:**
```bash
source venv/bin/activate
python scripts/production/scene_image_generator.py \
  --storyboard logs/storyboards/LATEST.json --dry-run
```

**.env key:** `FAL_API_KEY`

---

## OpenAI (DALL-E 3)

**Used for:** Fallback image generation if fal.ai fails.

**Get key:** [platform.openai.com](https://platform.openai.com) → API Keys

**Cost:** ~$0.040/image (standard) — much more expensive than fal.ai; avoid as primary.

**.env key:** `OPENAI_API_KEY`

---

## Runway ML (cinematic style)

**Used for:** AI video generation — Gen-3 Alpha Turbo, text-to-video.

**Get key:** [runwayml.com](https://runwayml.com) → API Access

**Cost:** ~$0.05/second of video → ~$0.15–0.30/scene (5–10s clips)

**Install:** `pip install runwayml`

**Status:** Scaffold implemented in `scene_generators/cinematic.py` — ready when key is added.

**.env key:** `RUNWAY_API_KEY`

---

## Google Veo

**Used for:** Cinematic video generation (higher quality than Runway).

**Status:** Scaffold only — Veo API is in private preview as of 2026-04. Not yet publicly available.

**.env key:** `GOOGLE_API_KEY` (or `VERTEX_PROJECT_ID` + `VERTEX_LOCATION`)

---

## YouTube Data API v3

**Used for:** Uploading finished shorts + scheduling.

**Get credentials:**
1. [console.cloud.google.com](https://console.cloud.google.com) → Create project
2. Enable YouTube Data API v3
3. OAuth 2.0 credentials → Desktop app
4. Download JSON → set path in `.env`

**Authenticate:**
```bash
python scripts/publishing/youtube_uploader.py --auth
```

**.env keys:** `YOUTUBE_CLIENT_SECRETS` (path to JSON), `YOUTUBE_TOKEN` (auto-generated after auth)

---

## Whisper (local)

**Used for:** Voiceover transcription for caption word timestamps.

**Install:** `pip install openai-whisper` (already in venv)

**Model used:** `small` — good speed/accuracy balance on CPU.

**No API key needed** — runs locally.

---

## ffmpeg (system)

**Used for:** Ken Burns animation, video concat, caption burn, audio mux.

**Install:** `sudo apt install ffmpeg`

**Test:** `ffmpeg -version`

**No API key needed.**

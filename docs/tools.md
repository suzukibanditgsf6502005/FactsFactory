# Tools & APIs

> Wszystkie narzędzia używane przez PawFactory. Dla każdego: jak uzyskać klucz, limity, koszt, jak testować.

---

## 1. Anthropic API (Claude)

**Do czego:** Generowanie hooków, skryptów narracji, tytułów, opisów, research niszy.

**Jak uzyskać klucz:**
1. Wejdź na [console.anthropic.com](https://console.anthropic.com)
2. Zarejestruj konto
3. Settings → API Keys → Create Key
4. Skopiuj do `.env` jako `ANTHROPIC_API_KEY`

**Models in use:**
- `claude-sonnet-4-6` — hook generation, QC
- `claude-haiku-4-5-20251001` — music track selection, caption keyword analysis

**Koszt:** ~$0.003 per hook (input + output ~1500 tokenów)
- Przy 2 shortach/dzień = ~$0.18/mies — pomijalne

**Limity:** Rate limit na nowym koncie: 50 req/min — wystarczy z zapasem

**Test:**
```bash
python -c "
import anthropic, os
from dotenv import load_dotenv
load_dotenv()
c = anthropic.Anthropic()
r = c.messages.create(model='claude-sonnet-4-5', max_tokens=100, messages=[{'role':'user','content':'Say OK'}])
print(r.content[0].text)
"
```

---

## 2. ElevenLabs (AI Voiceover)

**Do czego:** Generowanie lektora AI dla każdego Shorta.

**Jak uzyskać klucz:**
1. Wejdź na [elevenlabs.io](https://elevenlabs.io)
2. Zarejestruj konto → wybierz plan **Starter ($5/mies)**
3. Profile → API Key → skopiuj
4. Do `.env` jako `ELEVENLABS_API_KEY`

**Current voice:** Lily (`pFZP5JQG7iQjIQuC4Bku`) — Velvety Actress, British, confident. Set as `ELEVENLABS_VOICE_ID` in `.env`.

**Previously tested:** Rachel (`21m00Tcm4TlvDq8ikWAM`) — replaced by Lily for more dramatic delivery.

**Koszt:** Plan Starter = $5/mies = 30 min audio
- 1 Short ≈ 40 sekund narracji
- 30 min = ~45 shortów/mies — wystarczy na początku
- Plan Creator ($22/mies) = 100 min gdy skalujesz

**Limity:** 20 req/min na Starterze

**Test:**
```bash
python scripts/production/voiceover.py --test
```

---

## 3. Reddit Sourcing — RSS (no API key required)

> **PRAW (Reddit API) was replaced by RSS in March 2026.**
> The old PRAW integration required app registration and was subject to policy restrictions.
> Current implementation uses public RSS feeds via `feedparser` + `requests` — no credentials needed.

**Script:** `scripts/sourcing/reddit_scraper.py`

**Active feeds (hot.rss):**
- r/AnimalsBeingBros, r/MadeMeSmile, r/HumansBeingBros, r/aww, r/rarepuppers, r/Eyebleach, r/rescue

**No `.env` keys needed for Reddit.** Remove `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` if present — they are unused.

**Test:**
```bash
python scripts/sourcing/reddit_scraper.py --test
```

**Note:** `r/rescue` returns 403 consistently — may be removed from `RSS_FEEDS` in the scraper.

---

## 4. yt-dlp (Video Downloader)

**Do czego:** Pobieranie filmów z Reddit, TikTok, Instagram, YouTube, 1000+ serwisów.

**Instalacja:**
```bash
# Ubuntu
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
  -o /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp

# Aktualizacja (rób co tydzień — serwisy często zmieniają API)
yt-dlp -U
```

**Koszt:** Darmowy, open source

**Konfiguracja w `.env`:** Nie wymaga klucza API

**Użycie w skryptach:**
```bash
# Pobierz najlepszą jakość do 1080p
yt-dlp -f "bestvideo[height<=1080]+bestaudio/best[height<=1080]" \
  --merge-output-format mp4 \
  --output "inbox/%(id)s.%(ext)s" \
  "URL"
```

**Test:**
```bash
yt-dlp --version
yt-dlp -f best --output "inbox/test.%(ext)s" "https://www.reddit.com/r/AnimalsBeingBros/comments/JAKIS_POST/"
```

---

## 5. ffmpeg (Video Processing)

**Do czego:** Konwersja do 9:16, dodawanie audio, nakładanie napisów, encoding.

**Instalacja:**
```bash
sudo apt install -y ffmpeg
```

**Koszt:** Darmowy, open source

**Kluczowe komendy używane w pipeline:**

```bash
# Konwersja do 9:16 + resize do 1080x1920
ffmpeg -i input.mp4 \
  -vf "crop=ih*9/16:ih,scale=1080:1920,setsar=1" \
  -c:v libx264 -preset fast -crf 22 \
  output_vertical.mp4

# Podmiana audio (voiceover 100% + oryginał 15%)
ffmpeg -i video.mp4 -i voiceover.mp3 \
  -filter_complex "[0:a]volume=0.15[orig];[1:a]volume=1.0[vo];[orig][vo]amix=inputs=2[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac \
  output_mixed.mp4

# Burn-in napisów z pliku SRT
ffmpeg -i video.mp4 \
  -vf "subtitles=captions.srt:force_style='FontSize=18,Bold=1,Alignment=2,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=1,Outline=2'" \
  output_captioned.mp4
```

**Test:**
```bash
ffmpeg -version
```

---

## 6. Whisper (Auto-captions, lokalne — darmowe)

**Do czego:** Transkrypcja audio do SRT dla napisów. Alternatywa dla Captions.ai.

**Instalacja:**
```bash
pip install openai-whisper
# Wymaga też: sudo apt install -y python3-dev
```

**Użycie:**
```bash
whisper audio.mp3 --model small --output_format srt --output_dir logs/captions/
```

**Modele:**
- `tiny` — najszybszy, mniej dokładny (ok dla prostej narracji)
- `small` — dobry balans (rekomendowany)
- `medium` — dokładniejszy, wolniejszy

**Koszt:** Darmowy (lokalnie), wymaga ~1-2 GB RAM per run

---

## 7. Buffer (Multi-platform scheduling)

**Do czego:** Schedulowanie postów na YouTube, TikTok, Instagram z jednego miejsca.

**Jak uzyskać klucz:**
1. Wejdź na [buffer.com](https://buffer.com)
2. Zarejestruj konto → plan **Essentials ($6/mies)**
3. Settings → API → Create Access Token
4. Do `.env` jako `BUFFER_ACCESS_TOKEN`
5. Połącz konta: YouTube, TikTok, Instagram

**Koszt:** $6/mies (Essentials — 3 kanały, unlimited posts)

**Limity:** API rate limit: 60 req/min

**Uwaga:** Buffer obsługuje schedulowanie, ale upload wideo na TikTok przez API wymaga dodatkowej weryfikacji. Na początku TikTok wrzucaj ręcznie.

---

## 8. YouTube Data API

**Do czego:** Analytics (views, CTR, AVD), opcjonalnie upload.

**Jak uzyskać klucz:**
1. Wejdź na [console.cloud.google.com](https://console.cloud.google.com)
2. Utwórz nowy projekt: `PawFactory`
3. APIs & Services → Enable APIs → szukaj "YouTube Data API v3" → Enable
4. Credentials → Create Credentials → API Key
5. Do `.env` jako `YOUTUBE_API_KEY`

**Koszt:** Darmowy (10,000 units/dzień — wystarczy)

**Limity:** 10,000 quota units/dzień. Odczyt statystyk = ~1-5 units per call.

---

## 9. Opus Clip (Smart clipping) — opcjonalny

**Do czego:** Automatyczne wykrywanie najlepszych momentów z długich filmów.

**Jak uzyskać klucz:**
1. [opus.pro](https://opus.pro) → Sign up
2. Plan **Starter ($19/mies)** — 150 min/mies
3. Settings → API (beta) → Generate Key
4. Do `.env` jako `OPUS_CLIP_API_KEY`

**Uwaga:** API Opus Clip jest w beta — funkcjonalność może być ograniczona. Na początek można pominąć i używać yt-dlp + ffmpeg do cięcia.

---

## 10. Submagic (Primary Caption API)

**Purpose:** Word-by-word captions with highlights. Sara template. Primary caption path in `video_editor.py`.

**How it works:** Video uploaded to catbox.moe (24h temp host) → POST to Submagic API → poll for completion → download captioned video.

**Key setting:** `cleanAudio=False` — preserves ElevenLabs voiceover (does not replace with Submagic TTS).

**Cost:** Consumes project minutes per video. Check balance at submagic.co before production runs.

**Config:** `SUBMAGIC_API_KEY` in `.env`

**Fallback:** If Submagic fails or key is absent, `video_editor.py` automatically uses ASS v2 captions (free, local).

---

## 11. Captions.ai — NOT IN USE

> Captions.ai is NOT used. The current fallback caption system is ASS v2 (`ass_captions.py`) using Whisper + Claude Haiku + ffmpeg. No external caption API other than Submagic is needed.

---

## Podsumowanie — co kupić na start (PoC)

| Narzędzie | Koszt | Priorytet |
|-----------|-------|-----------|
| Anthropic API | Pay-per-use (~$1/mies) | ✅ Konieczny |
| ElevenLabs Starter | $5/mies | ✅ Konieczny |
| Reddit API | Darmowy | ✅ Konieczny |
| yt-dlp + ffmpeg | Darmowy | ✅ Konieczny |
| Whisper | Darmowy | ✅ Konieczny |
| Buffer Essentials | $6/mies | ⏳ Gdy masz co schedulować |
| YouTube Data API | Darmowy | ⏳ Gdy masz kanał |
| Opus Clip | $19/mies | ⏳ Później |
| Captions.ai | $13/mies | ⏳ Później |

**Koszt startu: ~$6–11/mies**

---

## .env.example

The canonical `.env.example` lives at the repo root. Key variables:

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Hook gen, QC, music select, caption analysis |
| `ELEVENLABS_API_KEY` | ✅ | Voiceover TTS |
| `ELEVENLABS_VOICE_ID` | ✅ | `pFZP5JQG7iQjIQuC4Bku` (Lily) |
| `SUBMAGIC_API_KEY` | ⚡ | Primary captions; omit to use free ASS v3 fallback |
| `OPENAI_API_KEY` | ⏳ | Optional — enables OpenAI QA provider (`--provider openai`) |
| `YOUTUBE_API_KEY` | ⏳ | Analytics only; not needed until channel launched |
| `INBOX_DIR` | — | Default: `./inbox` |
| `OUTPUT_DIR` | — | Default: `./output` |
| `LOG_DIR` | — | Default: `./logs` |

**Not needed:** `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` (replaced by RSS), `CAPTIONS_AI_API_KEY` (not used), `BUFFER_ACCESS_TOKEN` (manual upload in use), `OPUS_CLIP_API_KEY` (not integrated).

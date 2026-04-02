# PawFactory Setup Log

**Date:** 2026-03-25
**Operator:** Claude Code (autonomous setup)

---

## STEP 1: System update

```
sudo apt update && sudo apt upgrade -y
```

**Result:** ✅ System already up to date. 0 packages upgraded.

---

## STEP 2: Core system packages

```
sudo apt install -y git curl wget unzip htop tmux nano build-essential software-properties-common python3 python3-pip python3-venv python3-dev
```

**Result:** ✅ All packages installed.
- `python3 --version` → Python 3.12.3
- `git --version` → git version 2.43.0

---

## STEP 3: ffmpeg

```
sudo apt install -y ffmpeg
```

**Result:** ✅ ffmpeg installed.
- `ffmpeg -version` → ffmpeg version 6.1.1-3ubuntu5

---

## STEP 4: yt-dlp

```
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp
```

**Result:** ✅ yt-dlp installed.
- `yt-dlp --version` → 2026.03.17

---

## STEP 5: Node.js 20 LTS

```
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

**Note:** Node.js 18.19.1 was already installed — upgraded to v20 via NodeSource repo.

**Result:** ✅ Node.js 20 installed.
- `node --version` → v20.20.1
- `npm --version` → 10.8.2

---

## STEP 6: Claude Code CLI

```
sudo npm install -g @anthropic-ai/claude-code
```

**Note:** Initial `npm install -g` failed with permissions error — resolved by using `sudo`.

**Result:** ✅ Claude Code CLI installed.
- `claude --version` → 2.1.81 (Claude Code)

---

## STEP 7: Python virtual environment

```
python3 -m venv venv
source venv/bin/activate
```

**Result:** ✅ Virtual environment created at `./venv`

---

## STEP 8: Python packages

```
pip install --upgrade pip
pip install praw anthropic requests python-dotenv rich typer elevenlabs ffmpeg-python schedule
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install openai-whisper
```

**Result:** ✅ All packages installed.

| Package | Version |
|---------|---------|
| anthropic | 0.86.0 |
| elevenlabs | 2.40.0 |
| openai-whisper | 20250625 |
| praw | 7.8.1 |
| python-dotenv | 1.2.2 |
| requests | 2.32.5 |
| rich | 14.3.3 |
| torch | 2.11.0+cpu |

---

## STEP 9: requirements.txt

```
pip freeze > requirements.txt
git add requirements.txt
git commit -m "chore: add requirements.txt after environment setup"
```

**Result:** ✅ requirements.txt generated (55 packages) and committed. Commit: `8d0d7d0`

---

## STEP 10: .env file

```
cp .env.example .env
```

**Result:** ✅ `.env` created from template. **Action required:** Fill in API keys before running pipeline.

---

## STEP 11: Runtime directories

```
mkdir -p inbox output logs logs/hooks logs/captions
touch inbox/.gitkeep output/.gitkeep
```

**Result:** ✅ Directories created: `inbox/`, `output/`, `logs/`, `logs/hooks/`, `logs/captions/`

---

## STEP 12: Final verification

| Check | Command | Result |
|-------|---------|--------|
| Python | `python3 --version` | ✅ Python 3.12.3 |
| Node.js | `node --version` | ✅ v20.20.1 |
| ffmpeg | `ffmpeg -version` | ✅ 6.1.1-3ubuntu5 |
| yt-dlp | `yt-dlp --version` | ✅ 2026.03.17 |
| Claude CLI | `claude --version` | ✅ 2.1.81 (Claude Code) |
| Python packages | `import praw, anthropic, whisper, rich` | ✅ All packages OK |

---

## STEP 13: Setup Summary

**Setup completed:** 2026-03-25 05:09 UTC

**OS:** Ubuntu 24.04.4 LTS (Noble Numbat) — Linux 6.17.0-19-generic

**All checks passed:** ✅ 6/6

**Issues encountered and resolved:**

1. `npm install -g @anthropic-ai/claude-code` — failed with permissions error on `/usr/lib/node_modules/@anthropic-ai`. Fixed by using `sudo npm install -g`.
2. Node.js 18.19.1 was pre-installed but version 20 was required. Resolved by adding NodeSource v20 repo and reinstalling.

**Full Python package list (venv):**

| Package | Version |
|---------|---------|
| annotated-doc | 0.0.4 |
| annotated-types | 0.7.0 |
| anthropic | 0.86.0 |
| anyio | 4.13.0 |
| certifi | 2026.2.25 |
| charset-normalizer | 3.4.6 |
| click | 8.3.1 |
| distro | 1.9.0 |
| docstring_parser | 0.17.0 |
| elevenlabs | 2.40.0 |
| ffmpeg-python | 0.2.0 |
| filelock | 3.25.2 |
| fsspec | 2026.2.0 |
| future | 1.0.0 |
| h11 | 0.16.0 |
| httpcore | 1.0.9 |
| httpx | 0.28.1 |
| idna | 3.11 |
| Jinja2 | 3.1.6 |
| jiter | 0.13.0 |
| llvmlite | 0.46.0 |
| markdown-it-py | 4.0.0 |
| MarkupSafe | 3.0.2 |
| mdurl | 0.1.2 |
| more-itertools | 10.8.0 |
| mpmath | 1.3.0 |
| networkx | 3.6.1 |
| numba | 0.64.0 |
| numpy | 2.4.3 |
| openai-whisper | 20250625 |
| pip | 26.0.1 |
| praw | 7.8.1 |
| prawcore | 2.4.0 |
| pydantic | 2.12.5 |
| pydantic_core | 2.41.5 |
| Pygments | 2.19.2 |
| python-dotenv | 1.2.2 |
| regex | 2026.2.28 |
| requests | 2.32.5 |
| rich | 14.3.3 |
| schedule | 1.2.2 |
| setuptools | 70.2.0 |
| shellingham | 1.5.4 |
| sniffio | 1.3.1 |
| sympy | 1.14.0 |
| tiktoken | 0.12.0 |
| torch | 2.11.0+cpu |
| tqdm | 4.67.3 |
| triton | 3.6.0 |
| typer | 0.24.1 |
| typing_extensions | 4.15.0 |
| typing-inspection | 0.4.2 |
| update-checker | 0.18.0 |
| urllib3 | 2.6.3 |
| websocket-client | 1.9.0 |
| websockets | 16.0 |

**Next steps:**
1. Fill in `.env` with API keys (ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
2. Run `source venv/bin/activate` before each session
3. Test individual scripts with `--test` flag before running full pipeline

---

## Post-setup configuration

- Added alias `cc` for `claude --dangerously-skip-permissions` to ~/.bashrc
- Status: READY FOR API KEYS
- Next step: Fill .env with API keys

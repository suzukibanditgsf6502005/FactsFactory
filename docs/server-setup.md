# Server Setup — Ubuntu 24.04 LTS

> Kompletny setup serwera produkcyjnego dla SaveAnimalsFactory.
> Po wykonaniu tych kroków Claude Code będzie mógł operować pełnym stackiem.

---

## 1. Wybór i provisioning VPS

**Rekomendowany provider:** [Hetzner Cloud](https://www.hetzner.com/cloud)
- Model: **CPX31** — 4 vCPU, 8 GB RAM, 160 GB SSD NVMe — ~€13/mies
- Alternatywa tańsza: **CX22** — 2 vCPU, 4 GB RAM, 40 GB SSD — ~€4/mies (wystarczy na start)
- Lokalizacja: **Nuremberg lub Helsinki** (dobra łączność, GDPR-friendly)
- OS: **Ubuntu 24.04 LTS**

**Inne opcje:**
- DigitalOcean Droplet 4GB — $24/mies (drożej za to samo)
- Oracle Cloud Free Tier — darmowy, ale niestabilny i wolny
- Hetzner wygrywa stosunkiem ceny do jakości.

---

## 2. Pierwsze logowanie i hardening

```bash
# Zaloguj się jako root
ssh root@YOUR_SERVER_IP

# Utwórz użytkownika roboczego (nie pracuj jako root)
adduser factory
usermod -aG sudo factory

# Skopiuj swój klucz SSH do nowego użytkownika
rsync --archive --chown=factory:factory ~/.ssh /home/factory

# Wyloguj się i zaloguj jako factory
exit
ssh factory@YOUR_SERVER_IP

# Wyłącz logowanie hasłem (tylko klucze SSH)
sudo nano /etc/ssh/sshd_config
# Ustaw: PasswordAuthentication no
# Ustaw: PermitRootLogin no
sudo systemctl restart ssh

# Podstawowy firewall
sudo ufw allow OpenSSH
sudo ufw enable
sudo ufw status
```

---

## 3. System dependencies

```bash
sudo apt update && sudo apt upgrade -y

# Core tools
sudo apt install -y \
  git \
  curl \
  wget \
  unzip \
  htop \
  tmux \
  nano \
  build-essential \
  software-properties-common

# Python 3.12
sudo apt install -y python3 python3-pip python3-venv python3-dev

# ffmpeg (video processing)
sudo apt install -y ffmpeg

# yt-dlp (video downloader)
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp

# Node.js 20 LTS (potrzebny dla Claude Code)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify
python3 --version    # 3.12.x
ffmpeg -version      # 6.x
yt-dlp --version
node --version       # 20.x
```

---

## 4. Claude Code CLI

```bash
# Instalacja
npm install -g @anthropic-ai/claude-code

# Weryfikacja
claude --version

# Konfiguracja klucza API
# Utwórz plik środowiskowy
echo 'export ANTHROPIC_API_KEY="sk-ant-TWOJ_KLUCZ"' >> ~/.bashrc
source ~/.bashrc

# Test
claude --print "Powiedz cześć"
```

> **Uwaga:** Claude Code z flagą `--dangerously-skip-permissions` pozwala na pełny dostęp do systemu plików i wykonywanie komend. Używaj tylko na dedykowanym serwerze, nigdy na maszynie z danymi osobistymi.

```bash
# Alias dla łatwego uruchamiania
echo 'alias cc="claude --dangerously-skip-permissions"' >> ~/.bashrc
source ~/.bashrc
```

---

## 5. Repo setup

```bash
# Klucz SSH do GitHuba
ssh-keygen -t ed25519 -C "factory-server" -f ~/.ssh/github_factory
cat ~/.ssh/github_factory.pub
# Dodaj ten klucz w GitHub → Settings → SSH Keys

# Konfiguracja SSH
cat >> ~/.ssh/config << EOF
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_factory
EOF

# Klonowanie repo
cd ~
git clone git@github.com:TWOJ_USERNAME/PawFactory.git
cd PawFactory

# Globalna konfiguracja gita
git config --global user.name "Factory Server"
git config --global user.email "twoj@email.com"
```

---

## 6. Python environment

```bash
cd ~/PawFactory

# Utwórz virtualenv
python3 -m venv venv
source venv/bin/activate

# Zainstaluj zależności
pip install --upgrade pip
pip install \
  praw \
  yt-dlp \
  requests \
  python-dotenv \
  anthropic \
  elevenlabs \
  ffmpeg-python \
  schedule \
  rich \
  typer

# Zapisz do requirements.txt
pip freeze > requirements.txt
git add requirements.txt
git commit -m "chore: add requirements.txt"
git push
```

---

## 7. Konfiguracja zmiennych środowiskowych

```bash
# Utwórz .env na serwerze (nigdy nie commituj tego pliku!)
cd ~/PawFactory
cp .env.example .env
nano .env
```

Zawartość `.env`:
```env
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# ElevenLabs
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...

# Reddit API (utwórz app na reddit.com/prefs/apps)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=SaveAnimalsFactory/1.0

# YouTube Data API
YOUTUBE_API_KEY=...

# Buffer
BUFFER_ACCESS_TOKEN=...

# Opus Clip
OPUS_CLIP_API_KEY=...

# Captions.ai
CAPTIONS_AI_API_KEY=...

# Paths
INBOX_DIR=/home/factory/PawFactory/inbox
OUTPUT_DIR=/home/factory/PawFactory/output
LOG_DIR=/home/factory/PawFactory/logs
```

```bash
# Dodaj .env do .gitignore
echo ".env" >> .gitignore
echo "inbox/" >> .gitignore
echo "output/" >> .gitignore
echo "logs/" >> .gitignore
git add .gitignore
git commit -m "chore: update gitignore"
git push
```

---

## 8. Struktura katalogów

```bash
cd ~/PawFactory
mkdir -p inbox output logs shorts scripts/sourcing scripts/production scripts/publishing scripts/analytics docs tools

# Pliki placeholder
touch inbox/.gitkeep output/.gitkeep logs/.gitkeep shorts/log.md

git add .
git commit -m "chore: initialize directory structure"
git push
```

---

## 9. tmux — praca bez rozłączania sesji

```bash
# Nowa sesja nazwana
tmux new -s factory

# Wewnątrz tmux — Claude Code zawsze działa, nawet po rozłączeniu SSH
cc  # uruchamia Claude Code

# Odłącz sesję: Ctrl+B, potem D
# Powrót do sesji:
tmux attach -t factory
```

---

## 10. Cron jobs (harmonogram automatyczny)

```bash
crontab -e
```

Dodaj:
```cron
# Scraping Reddit codziennie o 7:00
0 7 * * * cd /home/factory/PawFactory && source venv/bin/activate && python scripts/sourcing/reddit_scraper.py >> logs/cron.log 2>&1

# Stats tracker codziennie o 22:00
0 22 * * * cd /home/factory/PawFactory && source venv/bin/activate && python scripts/analytics/stats_tracker.py >> logs/cron.log 2>&1
```

---

## 11. Weryfikacja całego stacku

```bash
# Sprawdź wszystkie narzędzia
python3 --version
node --version
ffmpeg -version
yt-dlp --version
claude --version

# Test pobrania wideo
yt-dlp -f "best[height<=1080]" --output "inbox/test.%(ext)s" "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Test Claude Code
cc --print "Wylistuj pliki w katalogu ~/PawFactory"
```

---

## Podsumowanie — co masz po tym setupie

| Komponent | Status |
|-----------|--------|
| Ubuntu 24.04 hardened | ✅ |
| Python 3.12 + venv | ✅ |
| ffmpeg + yt-dlp | ✅ |
| Node.js 20 | ✅ |
| Claude Code CLI | ✅ |
| GitHub SSH access | ✅ |
| .env z kluczami API | ✅ |
| tmux dla persistent sessions | ✅ |
| Cron jobs | ✅ |
| Struktura katalogów | ✅ |

**Serwer jest gotowy. Claude Code może przejąć operacje.**

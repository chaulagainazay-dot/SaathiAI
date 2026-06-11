# SaathiAI 🎙️

Ajay's personal bilingual (Nepali + English) voice agent. Runs in the background on the
MacBook; usable by voice from the phone (PWA) and the Mac browser.

## What it does
- **Talks like a friend** in Nepali, English, or mixed — replies in your language.
- **Knows your work**: queries HCGMS canteen data live from Supabase (sales vs NPR 30k
  target, missing reports, credit alerts, hygiene, 5:30am duty).
- **Executes tasks**: opens Mac apps, runs macOS Shortcuts, types for you, triggers any
  n8n workflow, sends Telegram messages, manages your task list.
- **Creates content**: drafts Facebook/LinkedIn posts and YouTube scripts in your voice,
  reads them back, and posts via n8n **only after you approve**.
- **Recognizes YOUR voice**: speaker verification (resemblyzer embeddings). Unverified
  voices can chat but cannot post, control the Mac, or change data.
- **English coach**: say "English practice" — it converses, corrects you kindly, and
  tracks your recurring mistakes for review ("english progress").
- **Remembers**: long-term facts, conversation history, tasks — in a local SQLite db.

## Setup (one time, ~20 min)

```bash
cd ~/SaathiAI
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[voice]"
cp .env.example .env   # fill in ANTHROPIC_API_KEY + Supabase keys
```

1. **Voice engines are fully local** — faster-whisper for speech recognition
   (Nepali + English, auto-detected) and macOS `say` (English) / gTTS (Nepali) for
   speech output. Nothing to install beyond `pip install -e ".[voice]"` and
   `brew install ffmpeg portaudio` (already done). OmniVoice Studio can be plugged
   in later for premium cloned voices.
2. **Enroll your voice**: `python scripts/enroll_voice.py` (speak 30s, both languages).
3. **n8n** (for social posting): `docker run -d -p 5678:5678 -v ~/.n8n:/home/node/.n8n n8nio/n8n`
   Create a webhook workflow named `social-post` that branches on `platform` and posts
   via Facebook Pages API / LinkedIn API / YouTube Data API. Credentials live in n8n only.
4. **Run**:
   - **Hands-free terminal mode** (wake word, no touching anything):
     `.venv/bin/python -m saathi.listener` — then just say
     *"Saathi, aaja ko sales kati bhayo?"* out loud. After Saathi replies, a 12-second
     follow-up window stays open so you can keep talking without repeating the wake word.
   - **Server + phone PWA**: `.venv/bin/python -m saathi.server` → open
     http://localhost:8765 (Mac) or `http://<mac-ip>:8765` on your phone → Add to Home Screen.
5. **Background service** (starts at login, restarts if it crashes):
   ```bash
   cp scripts/com.ajay.saathiai.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.ajay.saathiai.plist
   ```

## Phone access from anywhere
On the same Wi-Fi, `http://<mac-ip>:8765` works directly. From outside, use Tailscale
(free, easiest) or your existing No-IP DUC setup. Note: phone browsers require HTTPS for
the microphone — Tailscale + `tailscale cert` or a Cloudflare Tunnel solves this.

## Try saying
- "Aaja ko sales kati bhayo?" → live Supabase numbers vs target
- "Who hasn't submitted their report?"
- "Draft a Facebook post about today's special momo" → draft → "post it"
- "Open Safari" / "Run my Morning shortcut"
- "Remind me to call the vegetable vendor tomorrow"
- "English practice garam" → coach mode

## Architecture
```
Phone PWA / Mac browser
        │ (audio or text)
        ▼
FastAPI server (saathi/server.py)
  ├── voice.py: OmniVoice STT/TTS + speaker verification
  ├── agent.py: Claude tool-use loop (claude-sonnet-4-6)
  ├── memory.py: SQLite — history, facts, mistakes, tasks
  └── tools/: canteen (Supabase) · content (draft/post) · n8n ·
              mac_control · notes · english
```

## Safety rules (built in)
- Privileged tools (posting, Mac control, n8n, Telegram) require a verified voice match.
- Saathi never posts without reading the draft back and getting explicit approval.
- No financial execution — ever. Reports and signals only.

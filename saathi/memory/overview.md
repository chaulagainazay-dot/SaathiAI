# Overview

## What Baadar is
Baadar is Ajay Chaulagain's personal AI assistant running on his Mac in Kathmandu.
It combines voice control, Mac automation, content creation, and canteen management
into one always-on assistant accessible via web UI (localhost:8765) and Telegram.

## Who uses it
- **Ajay** (primary) — canteen owner, pielts IELTS app builder, preparing to go abroad
- **Sajana** (canteen) — Ajay's wife, manages counter and credit

## The three projects Baadar serves
1. **pielts** (https://pielts.web.app) — IELTS practice app with Mr. Yeti persona
   - YouTube channel: @pieltsapp (UCn_iedVQ-suLE0hlRmszklg)
   - Daily content: 1 YouTube Short + 1 Facebook post + Instagram + blog
2. **HCG Canteen** — Hamro Chamena Griha, hospital canteen, NPR 30k/day target
   - System: HCGMS (Next.js + Supabase PWA)
3. **Crypto signal agent** — signals only, no auto-trading

## Current state (Jun 2026)
- FastAPI server at port 8765, voice + text + image generation
- Groq (llama) as primary LLM for speed
- Pollinations.ai (Flux) for free image generation
- Telegram two-way control (@AjayGmailbot, chat 919874672)
- Internet tools: web search, YouTube, GitHub, RSS via internet_reach.py
- Image generation endpoint: /api/v1/generate_image (Mr. Yeti styles built in)

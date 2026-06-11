"""SaathiAI configuration — loaded from environment / .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# --- Brain ---
# Free option: Google Gemini (free tier at aistudio.google.com).
# If GOOGLE_API_KEY is set, Gemini is used; otherwise falls back to Claude.
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
# Fully-local brain via Ollama (no internet, no API key, 100% private)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
# Pick brain: set LLM_PROVIDER=ollama|gemini|anthropic in .env to force one;
# otherwise Gemini if a key is set, else Claude.
LLM_PROVIDER = os.getenv("LLM_PROVIDER") or (
    "gemini" if GOOGLE_API_KEY and not GOOGLE_API_KEY.startswith("YOUR")
    else "anthropic")

# --- Voice (OmniVoice Studio local server, or fallbacks) ---
# OmniVoice exposes local STT/TTS; point these at its API once running.
OMNIVOICE_URL = os.getenv("OMNIVOICE_URL", "http://127.0.0.1:8920")
TTS_VOICE_EN = os.getenv("TTS_VOICE_EN", "saathi_en")
TTS_VOICE_NE = os.getenv("TTS_VOICE_NE", "saathi_ne")

# --- Speaker verification ---
# Only Ajay's voice can run privileged tools. Enroll with scripts/enroll_voice.py
VOICE_PROFILE_PATH = ROOT / "data" / "owner_voice.npy"
SPEAKER_THRESHOLD = float(os.getenv("SPEAKER_THRESHOLD", "0.75"))

# --- HCGMS / Supabase ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# --- n8n automation ---
N8N_WEBHOOK_BASE = os.getenv("N8N_WEBHOOK_BASE", "http://127.0.0.1:5678/webhook")

# --- Telegram (notifications, same bot as HCGMS) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Server ---
HOST = os.getenv("SAATHI_HOST", "0.0.0.0")
PORT = int(os.getenv("SAATHI_PORT", "8765"))

# --- Memory ---
DB_PATH = ROOT / "data" / "saathi.db"

"""SaathiAI configuration — loaded from environment / .env file."""
import json
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# --- Firebase: support JSON content in env var (for cloud deployments) ---
_fb_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON", "")
_fb_file = ROOT / "firebase-admin.json"
if _fb_json_str and not _fb_file.exists():
    try:
        _tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
        json.dump(json.loads(_fb_json_str), _tmp)
        _tmp.close()
        os.environ.setdefault("FIREBASE_SA_KEY", _tmp.name)
    except Exception:
        pass

# --- Brain ---
# Free option: Google Gemini (free tier at aistudio.google.com).
# If GOOGLE_API_KEY is set, Gemini is used; otherwise falls back to Claude.
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
# flash-lite is markedly faster than flash for short voice turns (and higher
# free quota); flash is kept as the fallback / vision model.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
# Cheap proxy — routes Anthropic API calls to Groq (free) via anthropic-proxy
CHEAP_PROXY_URL = os.getenv("CHEAP_PROXY_URL", "http://localhost:8788")
USE_CHEAP_PROXY = os.getenv("USE_CHEAP_PROXY", "0") == "1"
# Groq — fastest brain (~0.3s), free tier, runs Llama/Qwen on LPU hardware
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
# Fully-local brain via Ollama (no internet, no API key, 100% private)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
# Pick brain: set LLM_PROVIDER=groq|gemini|ollama|anthropic in .env to force one;
# otherwise Groq if keyed (fastest), then Gemini, then Claude.
LLM_PROVIDER = os.getenv("LLM_PROVIDER") or (
    "groq" if GROQ_API_KEY and not GROQ_API_KEY.startswith("YOUR")
    else "gemini" if GOOGLE_API_KEY and not GOOGLE_API_KEY.startswith("YOUR")
    else "anthropic")

# --- Voice (OmniVoice Studio local server, or fallbacks) ---
# OmniVoice exposes local STT/TTS; point these at its API once running.
OMNIVOICE_URL = os.getenv("OMNIVOICE_URL", "http://127.0.0.1:8920")
TTS_VOICE_EN = os.getenv("TTS_VOICE_EN", "saathi_en")
TTS_VOICE_NE = os.getenv("TTS_VOICE_NE", "saathi_ne")

# --- Speaker verification ---
# Only Ajay's voice can run privileged tools. Enroll with scripts/enroll_voice.py
VOICE_PROFILE_PATH = ROOT / "data" / "owner_voice.npy"


def _speaker_threshold() -> float:
    """Auto-tuned value (data/tuning.json) wins over the .env default."""
    base = float(os.getenv("SPEAKER_THRESHOLD", "0.75"))
    tuning = ROOT / "data" / "tuning.json"
    if tuning.exists():
        try:
            import json
            v = json.loads(tuning.read_text()).get("speaker_threshold")
            if v:
                return float(v)
        except Exception:
            pass
    return base


SPEAKER_THRESHOLD = _speaker_threshold()

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
PORT = int(os.getenv("PORT", os.getenv("SAATHI_PORT", "8765")))

# --- Memory ---
DB_PATH = ROOT / "data" / "saathi.db"

# --- Internal auth bypass (server calling its own API: health check, stage_draft) ---
SAATHI_TOKEN = os.getenv("SAATHI_TOKEN", "")

# --- GitHub Actions (for live status in Baadar UI) ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO  = os.getenv("GITHUB_REPO", "chaulagainazay-dot/SaathiAI")

# --- MailerLite (email list backup) ---
MAILERLITE_API_KEY  = os.getenv("MAILERLITE_API_KEY", "")
MAILERLITE_GROUP_ID = os.getenv("MAILERLITE_GROUP_ID", "")

# --- Firebase Storage (cloud video/thumbnail storage, free 5GB, no card needed) ---
# Bucket name auto-derived from firebase-admin.json project_id if not set
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "")

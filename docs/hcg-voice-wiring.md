# HCG voice transcribe — wiring into SaathiAI

Companion to `saathi/tools/hcg_voice.py` (this commit). Wires the new
`POST /api/v1/voice/transcribe` endpoint into the existing FastAPI app.

## 1. Include the router in `saathi/server.py`

Open `saathi/server.py` and find the block of `app.include_router(...)`
calls near the top (around line 25–35, just after `app = FastAPI(...)`).
Add:

```python
try:
    from .tools.hcg_voice import router as hcg_voice_router
    app.include_router(hcg_voice_router)
except Exception as _e:
    print(f"[saathi] hcg_voice router unavailable: {_e}")
```

The try/except mirrors the pattern already used for `ielts_router` and
`bma_router` — if the new module has an import error, the rest of the
server still boots.

## 2. Set the shared secret

Add to `~/SaathiAI/.env`:

```
BAADAR_API_KEY=<paste the same string you put on Vercel for HCG>
```

If you haven't picked one yet:

```bash
openssl rand -hex 32
```

Use the output value on BOTH:
- HCG Vercel env: `BAADAR_API_KEY`
- SaathiAI `.env`: `BAADAR_API_KEY`

They must match — HCG sends it as `Authorization: Bearer <key>` in the
outbound transcribe call and SaathiAI verifies the same string on the
inbound `baadar-callback` (and vice versa).

Also confirm `GEMINI_API_KEY` is set if you want LLM intent extraction.
Without it, the endpoint still works — it falls back to a regex
classifier that always returns confidence `0.55` (below HCG's `0.85`
auto-act threshold, so nothing accidentally fires).

## 3. Install httpx if it isn't already

```bash
cd ~/SaathiAI
pip install httpx
```

(Most likely already installed.)

## 4. Restart Baadar

```bash
launchctl bootout gui/$(id -u)/com.ajay.saathiai.n8n
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ajay.saathiai.baadar.plist
```

If your Baadar plist is named differently, substitute. Or just:

```bash
# Find the FastAPI process
pgrep -fl "saathi.server"
# Kill + restart however your dev loop normally works
```

## 5. Smoke test

```bash
curl -X POST http://127.0.0.1:8765/api/v1/voice/transcribe \
  -H "Authorization: Bearer $BAADAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "audio_url": "https://file-examples.com/storage/feaade38cc66f7eb9fb53/2017/11/file_example_MP3_700KB.mp3",
    "context": "hcg_general",
    "voice_message_id": "00000000-0000-0000-0000-000000000000"
  }'
```

Should return:

```json
{
  "transcript": "...",
  "intent": "general",
  "entities": {"notes": "..."},
  "confidence": 0.55,
  "suggestedResponse": ""
}
```

(The specific intent / confidence depends on whether Gemini was reached.)

## 6. Try the real flow

1. Open HCG `/dashboard/kot`
2. Hold the mic button bottom-right, say "Table 4 extra gravy", release
3. Pick a category, send
4. Within ~3 seconds, the inbox row's "Transcribing…" should flip to the actual transcript
5. If the LLM is wired, confidence should be ≥ 0.85 and the entities should include `tableNumber: 4`

## Logs

Baadar logs are at `~/SaathiAI/data/n8n-app.log` (yes, n8n shares the
launchd target). New lines from this endpoint look like:

```
INFO saathi.tools.hcg_voice: hcg_voice transcribed in 1.42s · intent=table_request confidence=0.91
WARNING saathi.tools.hcg_voice: hcg_voice callback https://.../baadar-callback → 401: Unauthorized
```

## Failure modes

| What happens | What you'll see |
|---|---|
| `BAADAR_API_KEY` missing on either side | HCG outbound: 401 from Baadar; Baadar inbound (callback): rejected by HCG. Fix: set the same string both places. |
| Audio URL not reachable | Baadar returns 502 + posts `{"error": "..."}` to HCG's callback, which records it on `voice_messages.baadar_error`. |
| Audio >5 MB | Baadar returns 413. Same callback path. HCG storage bucket should reject these too. |
| Gemini key missing or rate-limited | Endpoint still returns a transcript — intent is the regex-fallback at confidence 0.55. HCG won't auto-act, but a recipient still sees the transcript. |
| OmniVoice (`voice.transcribe`) crashes | 500. Background callback with `{"error": "transcription failed: ..."}`. |

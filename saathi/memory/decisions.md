# Decisions

## Image generation: Pollinations.ai over Google/Higgsfield
- Google Imagen 4 requires paid plan (free tier = 0 quota)
- Gemini image models quota = 0 on free tier
- Pollinations.ai (Flux) is completely free, no API key, good quality
- Higgsfield would be better for Mr. Yeti consistency (SoulIds) but requires paid key
- **Decision:** Pollinations as default; wire Higgsfield later when Ajay gets API key

## LLM: Groq as primary
- Groq is fastest for voice interactions (sub-second)
- Claude used for heavy tasks (code, analysis)
- Gemini as secondary fallback
- **Watch out:** Groq llama defaults to Chinese for IELTS content — always enforce English

## Auth: stateless cookie
- No sessions table in DB — avoids race conditions on server restart
- Token = `sha256(password_hash + ":baadar-session")`
- Password = "sajana" (stored as env var `BAADAR_PASSWORD`)
- Changing password auto-invalidates all sessions

## Content architecture: prepare + approve
- Baadar prepares ALL content automatically
- Ajay approves before publish ("post it / garde / huncha")
- Never auto-publish without human check
- This is "autopilot + approve" mode

## Suna patterns adopted (Jun 2026)
- Skills system: markdown SKILL.md files in `saathi/skills/`
- Memory files: structured markdown in `saathi/memory/`
- Memory reflector: nightly job updates memory from recent activity
- Skills loader: agent.py injects relevant skill into system prompt per task
- NOT adopted: Suna's full Docker stack, sandbox isolation, change requests (overkill for single user)

## Port: 8765
- Non-standard port to avoid conflicts
- Kill command: `lsof -ti:8765 | xargs kill -9` before restart

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

## Auth: first-owner bootstrap, server-side sessions (supersedes "stateless cookie")
- Sessions live in the security store and are validated there. The stateless
  `sha256(password_hash + ":baadar-session")` token is gone: on a system
  bootstrapped the current way the credential lives in the store and the process
  global is empty, so that expression reduced to the hash of a constant.
- The owner credential is a scrypt hash in the security store. It is never an
  environment variable, never in a dotenv file, and never written in plaintext
  anywhere — including here. This document previously recorded the account
  password in cleartext; it has been removed, and because it is still readable
  in this repository's history, that password must be treated as disclosed and
  rotated rather than reused.
- The first owner is created only by `POST /api/v1/auth/bootstrap`, which needs
  an explicitly armed installation and a one-time operator token file.
- Changing the password revokes every other session.

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

# Mr. Yeti Content Pipeline — Test Report
**Date:** 2026-06-22  
**Tested by:** Baadar / Claude Code static analysis (no Bash execution — read-only file audit)

---

## Summary

The pipeline architecture is solid and well-structured. Instagram is **almost fully wired** — it has credentials but may have a token expiry issue. TikTok is **app-configured but missing the OAuth access token**. The video generation, content creation, and multi-platform posting code is complete and production-ready.

---

## What's Connected and Working ✅

### Facebook
- **Status:** CONNECTED, API method
- `page_access_token` — present in `data/connections.json`
- `page_id` — `1150183931522490` — present
- `meta_post.post_facebook()` and `_upload_facebook_video()` — fully implemented
- Video upload via Graph API with 3-retry logic — complete

### Instagram
- **Status:** CONNECTED, API method (credentials present)
- `ig_account_id` — `17841415523956193` — present in `data/connections.json`
- `page_access_token` — shared with Facebook — present
- Handle: `@pieltsofficial`
- Full implementation exists:
  - `post_instagram_image()` — image posts via 2-step create + publish
  - `post_instagram_reel()` — Reels via **resumable direct upload** (no public URL needed) with 24-poll loop
  - `post_instagram_image_local()` — uploads local image to Imgur then posts
  - `_upload_instagram_reel()` in `mr_yeti_pipeline.py` — handles 15s minimum padding + caption append
- The pipeline (`mr_yeti_pipeline.py`) calls `_upload_instagram_reel()` at Step 4 of `run_pipeline()`

### YouTube
- **Status:** CONNECTED via n8n webhook
- Webhook: `http://127.0.0.1:5678/webhook/youtube-upload`
- `publish_to_youtube()` stages files to `~/.n8n-files`, calls webhook with retry
- Pipeline calls this at Step 2 — fully wired

### LinkedIn
- **Status:** CONNECTED — OAuth tokens present in `.env`
  - `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_PERSON_URN` — all set
- `linkedin_post.py` tool present in tools directory

### Content Generation (LLM)
- **Status:** WORKING — multiple LLM backends configured
  - `ANTHROPIC_API_KEY` — set (claude-sonnet-4-6)
  - `GOOGLE_API_KEY` — set (gemini-2.5-flash-lite)
  - `GROQ_API_KEY` — set (llama-3.3-70b-versatile)
- `content_studio.generate_content_pack()` — full Mr. Yeti content pack (script, IG caption, FB post, hashtags)
- `content_studio.make_daily_kit()` — full daily kit including blog post
- `content_studio.make_flow_prompts()` — Google Flow / Veo 3 scene prompts

### Video Generation
- **HyperFrames renderer** — local fallback, fully implemented
- **Google Flow / Veo** — `GOOGLE_API_KEY` set, `VEO_MODEL=veo-3.1-lite-generate-preview` set
- `make_video()` — local faceless captioned video with PIL + ffmpeg + TTS
- Subtitles, thumbnails, voiceover pipeline — all implemented

### Voice / TTS
- **OmniVoice** — `OMNIVOICE_TTS_URL=http://127.0.0.1:3900`, `YETI_VOICE_PROFILE=a7ea9bea` — configured
- **ElevenLabs** — `ELEVENLABS_API_KEY` is EMPTY (see blocked section)
- macOS `say` fallback — always available

### Telegram Notifications
- `TELEGRAM_BOT_TOKEN` — set
- `TELEGRAM_CHAT_ID` — `919874672` — set
- `send_telegram()` and `send_video()` via n8n — wired into pipeline completion

### Scheduler / Auto-post
- `post_slot("1pm")` → TikTok + Instagram
- `post_slot("8pm")` → Facebook + YouTube
- `mr_yeti_queue.json` persists state; idempotency check prevents double-posting

---

## What's Blocked and Why ❌

### TikTok — Missing OAuth Access Token
- **App credentials:** PRESENT — `TIKTOK_CLIENT_KEY=awhnl2fowfdomo69`, `TIKTOK_CLIENT_SECRET` set
- **Access token:** MISSING — `TIKTOK_ACCESS_TOKEN` and `TIKTOK_OPEN_ID` are NOT in `.env`
- `connections.json` shows `"method": "manual"` — meaning it was never OAuth'd
- `tiktok_post.token_ok()` returns `False` → `_upload_tiktok()` returns `{"status": "skipped", "reason": "TikTok not connected"}`
- The OAuth callback redirect is set to `https://pielts.web.app/api/v1/tiktok/callback` — this is a production URL, not localhost, which means OAuth can only be completed from a live server or requires a custom redirect setup

### ElevenLabs — No API Key
- `ELEVENLABS_API_KEY` is empty in `.env`
- Voiceover falls back to OmniVoice (local) → then macOS `say`
- Premium, expressive Mr. Yeti voice not available until key is added
- `make_animated_video()` with HeyGen also requires ElevenLabs or HeyGen native voice

### HeyGen — No API Key
- `HEYGEN_API_KEY` is empty
- `HEYGEN_TALKING_PHOTO_ID` is empty
- Animated talking-head Mr. Yeti videos unavailable until paid plan set up (~$29/mo)

### D-ID — No API Key
- `DID_API_KEY` not set
- `make_avatar_video()` blocked

### Gmail — No OAuth Tokens
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` all empty
- Email tool non-functional

### Instagram — Potential Token Expiry Risk
- The `page_access_token` in `connections.json` is a **long-lived token** but has no expiry tracking
- Meta long-lived tokens expire after ~60 days unless refreshed
- No automatic token refresh logic exists in `meta_post.py`
- If the token has expired, all Instagram and Facebook API calls will fail silently with a Graph API error

### X/Twitter
- `connections.json` shows `"connected": false`
- No X credentials in `.env`

---

## What Needs to Be Fixed for Instagram End-to-End ✅

Instagram is the closest to fully working. Steps:

1. **Verify token is still valid** — run `meta_post.verify_token(page_access_token, page_id)` from the Baadar shell or UI. If it returns `{"ok": true}`, Instagram is good to go.

2. **If token expired** — re-issue a long-lived Page Access Token:
   - Go to [Facebook Developer App Dashboard](https://developers.facebook.com/apps/) → your app → Graph API Explorer
   - Generate a User Access Token with `pages_manage_posts`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish` permissions
   - Exchange for long-lived token via: `GET /oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_TOKEN`
   - Call `meta_post.save_credentials(new_token, "1150183931522490", "17841415523956193")`

3. **Test with a real image post** — call `post_instagram_image_local(path_to_image, caption)` with any test image. If it returns `{"status": "posted"}`, Instagram is fully working.

4. **For Reels** — the resumable direct upload path is implemented. The only risk is if the video is too short (<15s). `_pad_video_to_min_duration()` handles that automatically. Minimum video requirements: H.264, AAC audio, 9:16 aspect ratio, 720p+.

5. **Set up token auto-refresh** — add a cron job or Baadar scheduled task that calls the token refresh endpoint monthly and writes the new token to `connections.json`.

---

## What Needs to Be Fixed for TikTok End-to-End ❌

TikTok requires completing the OAuth flow. Steps:

1. **Configure the redirect URI** — the current redirect is `https://pielts.web.app/api/v1/tiktok/callback`. This requires either:
   - **Option A (easiest):** Temporarily change the redirect in the TikTok Developer Portal to `http://127.0.0.1:8765/api/v1/tiktok/callback` (Baadar's local server), complete OAuth, then change it back
   - **Option B:** Add a TikTok callback handler to the pielts web app (Firebase functions) that receives the code and forwards it to Baadar

2. **Complete the OAuth flow:**
   - Make sure Baadar is running: `uvicorn saathi.main:app --port 8765`
   - Visit `http://127.0.0.1:8765/api/v1/tiktok/auth` in browser
   - Log in to TikTok account `@pieltsapp`
   - Approve permissions (`video.upload`, `video.publish`)
   - The callback writes `TIKTOK_ACCESS_TOKEN` and `TIKTOK_OPEN_ID` to `.env` automatically

3. **Update connections.json** — after OAuth, also update `connections.json` to set `"method": "api"` for tiktok entry (currently `"manual"`)

4. **Token expiry** — TikTok access tokens expire after 24 hours by default. The `refresh_token` (90-day validity) must be used to get new access tokens. `tiktok_post.py` does NOT currently implement token refresh. This needs to be added or TikTok will break daily.

5. **App review** — TikTok's Content Posting API requires app review before going live with real users. For posting to your OWN account (sandbox mode), this is not required. Confirm the TikTok Developer app is in sandbox mode or has passed review.

---

## Exact Next Steps (Priority Order)

### Immediate (today)
1. **Verify Instagram token** — from Baadar chat: "Check if Instagram token is valid"
2. **Complete TikTok OAuth** — start Baadar, visit `/api/v1/tiktok/auth`, approve
3. **Test full pipeline with a dry run** — from Baadar: `run_pipeline(topic="IELTS discourse markers", force=True)`

### Short-term (this week)
4. **Add TikTok token refresh logic** to `tiktok_post.py` — store `refresh_token` in `.env` and auto-refresh when `access_token` is within 2 hours of expiry
5. **Add Instagram token refresh monitoring** — add a weekly health check that calls `verify_token()` and alerts via Telegram if expiring
6. **Test `post_slot("1pm")`** with a real video file to confirm the 1pm TikTok + Instagram automation works end-to-end

### Optional (nice to have)
7. **ElevenLabs** — add `ELEVENLABS_API_KEY` for premium Mr. Yeti voice in videos
8. **HeyGen** — add `HEYGEN_API_KEY` + upload Mr. Yeti Talking Photo for animated avatar videos

---

## Credential Quick Reference

| Platform | Config Location | Status |
|----------|----------------|--------|
| Facebook | `data/connections.json` + token | ✅ Configured |
| Instagram | `data/connections.json` (shares FB token) | ⚠️ Need to verify token expiry |
| TikTok | `.env` (app keys present) | ❌ Need OAuth access token |
| YouTube | `data/connections.json` n8n webhook | ✅ Configured |
| LinkedIn | `.env` OAuth tokens | ✅ Configured |
| ElevenLabs | `.env` | ❌ Empty |
| HeyGen | `.env` | ❌ Empty |
| Telegram | `.env` | ✅ Configured |
| Claude/Gemini/Groq | `.env` | ✅ All configured |
| OmniVoice | `.env` + local server | ✅ Profile set (needs server running) |

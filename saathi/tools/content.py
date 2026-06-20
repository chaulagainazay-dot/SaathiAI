"""Social content: drafting happens in the model; posting goes through n8n."""
import httpx

from .. import config

STYLE_NOTES = {
    "facebook": "Friendly, local, Nepali-English mix welcome. Short paragraphs, 1-3 emoji max, "
                "end with a question or call-to-action. Audience: Kathmandu locals, hospital "
                "staff, canteen customers.",
    "linkedin": "Professional but personal. English. Story-driven: small-business systems, "
                "building software for a real canteen, lessons learned. No hashtag spam (3 max).",
    "youtube": "Return JSON-ish sections: TITLE (clickable, honest), DESCRIPTION (2 paragraphs + "
               "chapters), SCRIPT (hook in first 15s, conversational, Nepali-English mix ok).",
}


def draft(platform: str, topic: str, language: str = "mixed", notes: str = "") -> dict:
    """The agent (Claude) writes the draft itself; this returns style guidance so the
    draft matches Ajay's voice and platform norms."""
    return {
        "instruction": "Write the draft now in your reply, following this style guide. "
                       "Read it back to Ajay and ask for approval before posting.",
        "platform": platform,
        "topic": topic,
        "language": language,
        "extra_notes": notes,
        "style_guide": STYLE_NOTES.get(platform, ""),
    }


def post(platform: str, content: str, title: str = "") -> dict:
    """Publish to ONE platform using its connected method. Only after Ajay approves."""
    from .. import connections
    cfg = connections.get_all().get(platform.lower(), {})
    method = cfg.get("method",
                     "browser" if platform.lower() in ("facebook", "linkedin") else "n8n")

    # YouTube is video-only — text posts don't upload via webhook
    if platform.lower() == "youtube":
        return {"status": "manual_upload", "platform": "youtube",
                "handle": cfg.get("handle", "@pieltsapp"),
                "note": "YouTube needs a video file. Use publish_to_youtube(video_path, title, description) to upload a video."}

    # Meta API — direct Graph API posting (no n8n needed)
    if method == "api" and platform.lower() in ("facebook", "instagram"):
        from . import meta_post
        if platform.lower() == "facebook":
            return meta_post.post_facebook(content)
        else:
            return meta_post.post_instagram_text(content)

    if method == "manual":
        return {"status": "manual_upload", "platform": platform,
                "handle": cfg.get("handle", ""),
                "note": f"Caption ready — upload the video to {cfg.get('handle') or platform} manually."}
    if method == "browser":
        from . import browser
        return browser.post(platform, content, title)
    # n8n: per-platform webhook if set, else the shared social-post webhook
    url = cfg.get("webhook") or f"{config.N8N_WEBHOOK_BASE}/post-social"
    # Payload matches 02-facebook-instagram-autopilot.json expectations
    payload = {
        "platform": platform.lower(),
        "text": content,
        "title": title,
        "instagram_caption": content if platform.lower() == "instagram" else "",
    }
    r = httpx.post(url, json=payload, timeout=60)
    r.raise_for_status()
    return {"status": "sent_to_n8n", "platform": platform,
            "n8n_response": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text}


def list_connections() -> dict:
    """Show which social platforms are connected and how each one posts."""
    from .. import connections
    return {"connections": connections.get_all(), "connected": connections.connected()}


def post_all(content: str, title: str = "", platforms: str = "") -> dict:
    """Post the SAME content to every connected platform at once (or a comma-separated
    subset). Only after Ajay approves the exact draft."""
    from .. import connections
    targets = ([p.strip().lower() for p in platforms.split(",") if p.strip()]
               or connections.connected())
    if not targets:
        return {"status": "no_targets",
                "message": "No platforms connected yet. Open Connections in Baadar "
                           "(the 🔗 link icon) to connect them."}
    results = {}
    for p in targets:
        try:
            results[p] = post(p, content, title)
        except Exception as e:
            results[p] = {"status": "error", "error": str(e)[:140]}

    # Build human-readable summary for the agent to display
    lines = []
    for p, r in results.items():
        status = r.get("status", "unknown")
        if status in ("sent", "sent_to_n8n", "published"):
            lines.append(f"✅ {p.capitalize()}: posted")
        elif status == "manual_upload":
            lines.append(f"📋 {p.capitalize()}: caption ready — upload manually to {r.get('handle', p)}")
        elif status == "error":
            lines.append(f"❌ {p.capitalize()}: failed — {r.get('error','unknown error')[:80]}")
        else:
            lines.append(f"⚠️ {p.capitalize()}: {status}")

    summary = "\n".join(lines) if lines else "No platforms posted."
    return {"posted_to": targets, "results": results, "summary": summary}

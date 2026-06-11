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
    """Publish a post. Facebook/LinkedIn go through the logged-in browser (no API
    keys needed). YouTube still routes through n8n. Only called after Ajay approves."""
    if platform.lower() in ("facebook", "linkedin"):
        from . import browser
        return browser.post(platform, content, title)
    # YouTube (and anything else) via n8n
    r = httpx.post(
        f"{config.N8N_WEBHOOK_BASE}/social-post",
        json={"platform": platform, "content": content, "title": title},
        timeout=60,
    )
    r.raise_for_status()
    return {"status": "sent_to_n8n", "platform": platform,
            "n8n_response": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text}

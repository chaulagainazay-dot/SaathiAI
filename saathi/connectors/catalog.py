"""Provider + capability catalog — the map of what SaathiOS can connect to.

Providers are grouped by category; each category exposes CAPABILITIES (verbs),
not raw APIs. Directors/Missions request a capability ("email.send"), never a
provider SDK. This catalog is metadata only — real OAuth/API wiring lives behind
adapters and is added provider-by-provider without touching anything above.
"""
from __future__ import annotations

# capability verbs per category (what a Director can ask for)
CAPABILITIES = {
    "email":     ["draft", "send", "reply", "search", "archive", "summarize"],
    "drive":     ["upload", "download", "search", "organize", "summarize"],
    "docs":      ["create", "read", "append", "export"],
    "sheets":    ["read", "append", "update", "chart"],
    "calendar":  ["create_event", "list", "update", "invite"],
    "social":    ["post", "schedule", "comment", "inbox", "analytics"],
    "video":     ["upload", "schedule", "thumbnail", "analytics"],
    "messaging": ["send", "channels", "groups", "bots"],
    "code":      ["repos", "issues", "pull_requests", "commits"],
    "analytics": ["report", "metrics", "search_console"],
    "payments":  ["charge", "subscriptions", "invoices", "payouts"],
    "ai":        ["generate", "embed", "image", "voice"],
    "hosting":   ["deploy", "logs", "status"],
    "crm":       ["contacts", "deals", "campaigns"],
}

# provider → category + auth type. auth: oauth | api_key | bot_token | smtp | none
PROVIDERS = {
    # Google suite
    "google":            ("identity", "oauth"),
    "gmail":             ("email", "oauth"),
    "google_drive":      ("drive", "oauth"),
    "google_docs":       ("docs", "oauth"),
    "google_sheets":     ("sheets", "oauth"),
    "google_calendar":   ("calendar", "oauth"),
    "google_analytics":  ("analytics", "oauth"),
    "google_search_console": ("analytics", "oauth"),
    "google_business":   ("social", "oauth"),
    "youtube":           ("video", "oauth"),
    # Meta
    "facebook":          ("social", "oauth"),
    "instagram":         ("social", "oauth"),
    "whatsapp":          ("messaging", "api_key"),
    "meta":              ("social", "oauth"),
    # other social
    "x":                 ("social", "oauth"),
    "linkedin":          ("social", "oauth"),
    "tiktok":            ("social", "oauth"),
    "telegram":          ("messaging", "bot_token"),
    "discord":           ("messaging", "bot_token"),
    "slack":             ("messaging", "oauth"),
    # dev / infra
    "github":            ("code", "oauth"),
    "supabase":          ("hosting", "api_key"),
    "cloudflare":        ("hosting", "api_key"),
    "vercel":            ("hosting", "api_key"),
    "firebase":          ("hosting", "api_key"),
    "n8n":               ("hosting", "api_key"),
    # AI providers
    "openai":            ("ai", "api_key"),
    "anthropic":         ("ai", "api_key"),
    "gemini":            ("ai", "api_key"),
    "google_ai_studio":  ("ai", "api_key"),
    "elevenlabs":        ("ai", "api_key"),
    "heygen":            ("ai", "api_key"),
    "runway":            ("ai", "api_key"),
    "fal":               ("ai", "api_key"),
    "piapi":             ("ai", "api_key"),
    "flow":              ("ai", "api_key"),
    # payments / crm / email infra
    "stripe":            ("payments", "api_key"),
    "hubspot":           ("crm", "oauth"),
    "mailchimp":         ("crm", "api_key"),
    "mailerlite":        ("crm", "api_key"),
    "brevo":             ("crm", "api_key"),
    "resend":            ("email", "api_key"),
    "twilio":            ("messaging", "api_key"),
    "smtp":              ("email", "smtp"),
    "imap":              ("email", "smtp"),
    # productivity
    "notion":            ("docs", "oauth"),
    "airtable":          ("sheets", "api_key"),
    "canva":             ("ai", "oauth"),
}

AUTH_TYPES = ("oauth", "api_key", "bot_token", "smtp", "none")


def provider_info(provider: str) -> dict:
    cat, auth = PROVIDERS.get(provider, ("", "none"))
    return {"provider": provider, "category": cat, "auth_type": auth,
            "capabilities": CAPABILITIES.get(cat, [])}


def catalog() -> list[dict]:
    return [provider_info(p) for p in sorted(PROVIDERS)]


def capabilities_for(provider: str) -> list[str]:
    cat = PROVIDERS.get(provider, ("", ""))[0]
    return CAPABILITIES.get(cat, [])

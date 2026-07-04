"""YouTube Studio page object — selectors only, with SELF-HEALING strategies.

Each element lists MULTIPLE strategies (comma-separated CSS = Playwright "match
any"): a stable id first, then aria-label, then placeholder/attribute fallbacks.
When YouTube renames a class or reorders the DOM, the next strategy still
matches — no code change, edit HERE only. (role=/text= engines and a vision
locator are the next resilience tier.)

⚠️ Verify against your logged-in Studio with a test clip; the returned step log
names any selector that failed so you know exactly which line to update.
"""

STUDIO_UPLOAD = "https://studio.youtube.com/channel/UC/videos/upload?d=ud"

# ── upload dialog ───────────────────────────────────────────────────────────
FILE_INPUT = "input[type='file']"

# ── details step (contenteditable boxes) — id → aria-label → attribute ───────
TITLE_BOX = (
    "#title-textarea #textbox, "
    "ytcp-social-suggestions-textbox[label='Title'] #textbox, "
    "#textbox[aria-label*='title' i], "
    "div[contenteditable='true'][aria-label*='title' i]"
)
DESCRIPTION_BOX = (
    "#description-textarea #textbox, "
    "ytcp-social-suggestions-textbox[label='Description'] #textbox, "
    "#textbox[aria-label*='description' i], "
    "div[contenteditable='true'][aria-label*='description' i]"
)
NOT_FOR_KIDS = (
    "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK'], "
    "#audience [name='VIDEO_MADE_FOR_KIDS_NOT_MFK'], "
    "tp-yt-paper-radio-button[aria-label*='not made for kids' i]"
)

# ── wizard navigation ───────────────────────────────────────────────────────
NEXT_BUTTON = "#next-button, ytcp-button#next-button, [aria-label='Next']"
DONE_BUTTON = "#done-button, ytcp-button#done-button"

# ── visibility step ─────────────────────────────────────────────────────────
def visibility_radio(level: str) -> str:
    lvl = level.upper()
    return (f"tp-yt-paper-radio-button[name='{lvl}'], "
            f"[name='{lvl}'], "
            f"tp-yt-paper-radio-button[aria-label*='{level}' i]")

PUBLISH_BUTTON = "#done-button, ytcp-button#done-button, [aria-label='Publish']"

# ── post-publish confirmation ───────────────────────────────────────────────
SHARE_URL = (
    "a.style-scope.ytcp-video-info, "
    ".ytcp-video-info a[href*='youtu'], "
    "a[href*='youtu.be']"
)
PROCESSING_STATUS = "ytcp-video-upload-progress, .ytcp-video-upload-progress"
CLOSE_DIALOG = "ytcp-button#close-button, #close-button"

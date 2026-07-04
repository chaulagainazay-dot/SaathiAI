"""YouTube Studio page object — selectors only.

⚠️ YouTube Studio's DOM changes periodically. These are the current-as-of-authoring
selectors; verify them against your logged-in Studio with a test clip and edit
HERE (nowhere else). Prefer stable attributes (aria-label, id) over generated
classes.
"""

STUDIO_UPLOAD = "https://studio.youtube.com/channel/UC/videos/upload?d=ud"

# ── upload dialog ───────────────────────────────────────────────────────────
FILE_INPUT = "input[type='file']"

# ── details step ────────────────────────────────────────────────────────────
# Studio uses contenteditable boxes, not plain inputs.
TITLE_BOX = "ytcp-social-suggestions-textbox[label='Title'] #textbox, #title-textarea #textbox"
DESCRIPTION_BOX = "ytcp-social-suggestions-textbox[label='Description'] #textbox, #description-textarea #textbox"

# "Not made for kids" (required to proceed)
NOT_FOR_KIDS = "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']"

# ── wizard navigation ───────────────────────────────────────────────────────
NEXT_BUTTON = "#next-button"                 # Details → Monetization → Checks → Visibility
DONE_BUTTON = "#done-button"

# ── visibility step ─────────────────────────────────────────────────────────
def visibility_radio(level: str) -> str:
    # level: "Public" | "Unlisted" | "Private"
    return f"tp-yt-paper-radio-button[name='{level.upper()}']"

PUBLISH_BUTTON = "#done-button"              # final publish/done

# ── post-publish confirmation ───────────────────────────────────────────────
SHARE_URL = "a.style-scope.ytcp-video-info, .ytcp-video-info a[href*='youtu']"
PROCESSING_STATUS = ".ytcp-video-upload-progress, ytcp-video-upload-progress"
CLOSE_DIALOG = "ytcp-button#close-button, #close-button"

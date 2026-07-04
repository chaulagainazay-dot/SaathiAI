"""TikTok page object — selectors only, multi-strategy (self-healing).

Uses TikTok Studio (not the iframed /upload). ⚠️ Verify against your logged-in
TikTok Studio with a test clip; edit HERE only.
"""

UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"

FILE_INPUT = "input[type='file']"
CAPTION = (".public-DraftEditor-content, "
           "div[contenteditable='true'][role='combobox'], "
           "div[contenteditable='true'], "
           "[data-e2e='video_caption'] div[contenteditable='true']")
POST_BUTTON = ("[data-e2e='post_video_button'], "
               "button:has-text('Post'), "
               "button[aria-label='Post']")
PROCESSING = "[class*='uploadProgress'], [data-e2e='upload-progress']"

KEYS = {
    "tiktok/file_input": FILE_INPUT,
    "tiktok/caption": CAPTION,
    "tiktok/post": POST_BUTTON,
}


def seed(registry) -> None:
    for key, sel in KEYS.items():
        registry.seed(key, [s.strip() for s in sel.split(",")])

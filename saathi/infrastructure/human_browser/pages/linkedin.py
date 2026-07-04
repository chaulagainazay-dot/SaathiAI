"""LinkedIn page object — selectors only, multi-strategy (self-healing).

⚠️ Verify against your logged-in LinkedIn with a draft post; edit HERE only.
"""

FEED = "https://www.linkedin.com/feed/"

START_POST = ("button.share-box-feed-entry__trigger, "
              "[aria-label='Start a post'], "
              "button:has-text('Start a post')")
EDITOR = (".ql-editor[contenteditable='true'], "
          "div[role='textbox'][contenteditable='true'], "
          "[aria-label*='Text editor' i]")
ADD_MEDIA = ("[aria-label='Add media'], "
             "button[aria-label*='add media' i], "
             "button[aria-label*='photo' i]")
MEDIA_INPUT = "input[type='file']"
MEDIA_DONE = ("button:has-text('Done'), "
              "button:has-text('Next'), "
              "[aria-label='Done']")
POST_BUTTON = ("button.share-actions__primary-action, "
               "[aria-label='Post'], "
               "button.share-box_actions button:has-text('Post')")

KEYS = {
    "linkedin/start_post": START_POST,
    "linkedin/editor": EDITOR,
    "linkedin/add_media": ADD_MEDIA,
    "linkedin/media_input": MEDIA_INPUT,
    "linkedin/media_done": MEDIA_DONE,
    "linkedin/post_button": POST_BUTTON,
}


def seed(registry) -> None:
    for key, sel in KEYS.items():
        registry.seed(key, [s.strip() for s in sel.split(",")])

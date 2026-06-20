"""Meta Graph API posting — Facebook Page + Instagram Business Account.
Stores credentials in data/connections.json under 'facebook' and 'instagram' keys.
Required fields:
  facebook.page_access_token  — long-lived Page Access Token
  facebook.page_id            — numeric Facebook Page ID
  instagram.ig_account_id     — numeric Instagram Business Account ID (linked to the Page)
"""
import json
from pathlib import Path

import httpx

_API = "https://graph.facebook.com/v19.0"


def _creds() -> dict:
    """Load Meta credentials from connections.json."""
    path = Path(__file__).parents[2] / "data" / "connections.json"
    try:
        data = json.loads(path.read_text())
        return {
            "token": data.get("facebook", {}).get("page_access_token", ""),
            "page_id": data.get("facebook", {}).get("page_id", ""),
            "ig_id": data.get("instagram", {}).get("ig_account_id", ""),
        }
    except Exception:
        return {"token": "", "page_id": "", "ig_id": ""}


def post_facebook(text: str, link: str = "") -> dict:
    """Post text (+ optional link) to the Facebook Page feed."""
    c = _creds()
    if not c["token"] or not c["page_id"]:
        return {"status": "error", "error": "Facebook not configured — need page_access_token and page_id"}
    payload = {"message": text, "access_token": c["token"]}
    if link:
        payload["link"] = link
    try:
        r = httpx.post(f"{_API}/{c['page_id']}/feed", data=payload, timeout=30)
        r.raise_for_status()
        post_id = r.json().get("id", "")
        return {"status": "posted", "platform": "facebook", "post_id": post_id,
                "url": f"https://facebook.com/{post_id.replace('_','/')}"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


def upload_image_public(local_path: str) -> str:
    """Upload a local image to Imgur (anonymous) and return the public URL."""
    import base64
    with open(local_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    r = httpx.post(
        "https://api.imgur.com/3/image",
        headers={"Authorization": "Client-ID 546c25a59c58ad7"},
        data={"image": b64, "type": "base64"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["data"]["link"]


def post_instagram_image_local(local_path: str, caption: str) -> dict:
    """Upload a local image to a public host then post it to Instagram."""
    try:
        public_url = upload_image_public(local_path)
    except Exception as e:
        return {"status": "error", "error": f"Image upload failed: {e}"}
    return post_instagram_image(public_url, caption)


def post_instagram_text(caption: str) -> dict:
    """Post a caption-only update to Instagram (no media — for text/reel captions)."""
    c = _creds()
    if not c["token"] or not c["ig_id"]:
        return {"status": "error", "error": "Instagram not configured — need page_access_token and ig_account_id"}
    # Instagram requires media; for caption-only, return it ready to copy
    return {"status": "manual_upload", "platform": "instagram",
            "caption": caption, "handle": "@pieltsapp",
            "note": "Instagram requires a photo/video. Caption is ready — upload manually or use post_instagram_image()."}


def post_instagram_image(image_url: str, caption: str) -> dict:
    """Post a photo to Instagram Business account via Graph API (image must be public URL)."""
    c = _creds()
    if not c["token"] or not c["ig_id"]:
        return {"status": "error", "error": "Instagram not configured"}
    try:
        # Step 1: Create media container
        r1 = httpx.post(f"{_API}/{c['ig_id']}/media",
                        data={"image_url": image_url, "caption": caption,
                              "access_token": c["token"]}, timeout=30)
        r1.raise_for_status()
        container_id = r1.json().get("id")
        if not container_id:
            return {"status": "error", "error": f"No container id: {r1.text[:200]}"}

        # Step 2: Publish
        r2 = httpx.post(f"{_API}/{c['ig_id']}/media_publish",
                        data={"creation_id": container_id, "access_token": c["token"]},
                        timeout=30)
        r2.raise_for_status()
        media_id = r2.json().get("id", "")
        return {"status": "posted", "platform": "instagram", "media_id": media_id}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


def post_instagram_reel(video_url: str, caption: str, thumbnail_url: str = "") -> dict:
    """Upload a Reel to Instagram via Graph API (video must be a public URL)."""
    c = _creds()
    if not c["token"] or not c["ig_id"]:
        return {"status": "error", "error": "Instagram not configured"}
    try:
        payload = {"media_type": "REELS", "video_url": video_url,
                   "caption": caption, "access_token": c["token"]}
        if thumbnail_url:
            payload["thumb_offset"] = "0"
        r1 = httpx.post(f"{_API}/{c['ig_id']}/media", data=payload, timeout=60)
        r1.raise_for_status()
        container_id = r1.json().get("id")
        if not container_id:
            return {"status": "error", "error": r1.text[:200]}

        # Poll until ready (up to 60s)
        import time
        for _ in range(12):
            time.sleep(5)
            status_r = httpx.get(f"{_API}/{container_id}",
                                 params={"fields": "status_code", "access_token": c["token"]},
                                 timeout=15)
            if status_r.json().get("status_code") == "FINISHED":
                break

        r2 = httpx.post(f"{_API}/{c['ig_id']}/media_publish",
                        data={"creation_id": container_id, "access_token": c["token"]},
                        timeout=30)
        r2.raise_for_status()
        return {"status": "posted", "platform": "instagram", "media_id": r2.json().get("id", "")}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


def save_credentials(page_access_token: str, page_id: str, ig_account_id: str) -> dict:
    """Save Meta credentials to connections.json and mark both platforms as connected."""
    path = Path(__file__).parents[2] / "data" / "connections.json"
    try:
        data = json.loads(path.read_text())
    except Exception:
        data = {}

    data.setdefault("facebook", {}).update({
        "connected": True, "method": "api",
        "handle": "pieltsapp",
        "page_access_token": page_access_token,
        "page_id": page_id,
        "webhook": ""
    })
    data.setdefault("instagram", {}).update({
        "connected": True, "method": "api",
        "handle": "@pieltsapp",
        "ig_account_id": ig_account_id,
        "webhook": ""
    })

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return {"ok": True, "facebook": "connected", "instagram": "connected"}


def verify_token(page_access_token: str, page_id: str) -> dict:
    """Test if the token works by fetching the Page name."""
    try:
        r = httpx.get(f"{_API}/{page_id}",
                      params={"fields": "name,id", "access_token": page_access_token},
                      timeout=15)
        r.raise_for_status()
        d = r.json()
        return {"ok": True, "page_name": d.get("name"), "page_id": d.get("id")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

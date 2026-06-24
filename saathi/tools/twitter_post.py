"""
Twitter/X posting — Mr. Yeti / pielts (@pieltsofficial)

Uses Twitter API v2 via tweepy.

One-time setup:
  1. Go to https://developer.twitter.com/en/portal/dashboard
  2. Create a Project + App, set App Permissions → Read and Write
  3. Generate Access Token & Secret (under "Keys and Tokens")
  4. Add to ~/SaathiAI/.env:
       TWITTER_API_KEY=...
       TWITTER_API_SECRET=...
       TWITTER_ACCESS_TOKEN=...
       TWITTER_ACCESS_TOKEN_SECRET=...

Text tweets: instant (free tier: 1,500 tweets/month).
Media tweets: upload image first via v1.1 media endpoint, then tweet.
"""
from __future__ import annotations

import os
from pathlib import Path

from .. import config


# ── Credentials ──────────────────────────────────────────────────────────────

def _api_key()            -> str: return os.environ.get("TWITTER_API_KEY", "")
def _api_secret()         -> str: return os.environ.get("TWITTER_API_SECRET", "")
def _access_token()       -> str: return os.environ.get("TWITTER_ACCESS_TOKEN", "")
def _access_token_secret()-> str: return os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")

def app_configured() -> bool:
    return all([_api_key(), _api_secret(), _access_token(), _access_token_secret()])

def status() -> dict:
    return {
        "app_configured": app_configured(),
        "handle": "@pieltsofficial",
        "missing": [k for k, v in {
            "TWITTER_API_KEY": _api_key(),
            "TWITTER_API_SECRET": _api_secret(),
            "TWITTER_ACCESS_TOKEN": _access_token(),
            "TWITTER_ACCESS_TOKEN_SECRET": _access_token_secret(),
        }.items() if not v],
    }


# ── Client builders ───────────────────────────────────────────────────────────

def _v2_client():
    import tweepy
    return tweepy.Client(
        consumer_key=_api_key(),
        consumer_secret=_api_secret(),
        access_token=_access_token(),
        access_token_secret=_access_token_secret(),
        wait_on_rate_limit=True,
    )

def _v1_api():
    """v1.1 API — needed for media uploads only."""
    import tweepy
    auth = tweepy.OAuth1UserHandler(
        _api_key(), _api_secret(),
        _access_token(), _access_token_secret()
    )
    return tweepy.API(auth, wait_on_rate_limit=True)


# ── Core posting ─────────────────────────────────────────────────────────────

def tweet(text: str) -> dict:
    """Post a plain text tweet. Returns {"status": "ok", "tweet_id": "..."}."""
    if not app_configured():
        return {"status": "error", "error": "Twitter credentials not configured — see twitter_post.py setup"}
    # Twitter v2 limit: 280 chars
    if len(text) > 280:
        text = text[:277] + "…"
    try:
        client = _v2_client()
        resp = client.create_tweet(text=text)
        tweet_id = resp.data["id"]
        return {"status": "ok", "tweet_id": tweet_id,
                "url": f"https://x.com/pieltsofficial/status/{tweet_id}"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


def tweet_with_image(text: str, image_path: str) -> dict:
    """Post a tweet with an attached image."""
    if not app_configured():
        return {"status": "error", "error": "Twitter credentials not configured"}
    if len(text) > 280:
        text = text[:277] + "…"
    try:
        api = _v1_api()
        media = api.media_upload(filename=image_path)
        client = _v2_client()
        resp = client.create_tweet(text=text, media_ids=[media.media_id])
        tweet_id = resp.data["id"]
        return {"status": "ok", "tweet_id": tweet_id,
                "url": f"https://x.com/pieltsofficial/status/{tweet_id}"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


# ── Caption builder ───────────────────────────────────────────────────────────

def build_tweet(hook: str, cta: str = "", hashtags: str = "") -> str:
    """Build a tweet ≤280 chars: hook + CTA + hashtags."""
    default_tags = "#IELTS #IELTSTips #pielts"
    tags = hashtags or default_tags
    cta_line = cta or "Free practice → pielts.web.app"

    # Build and trim to 280
    parts = [hook, "", cta_line, tags]
    full = "\n".join(parts)
    if len(full) <= 280:
        return full

    # Trim hashtags first
    parts = [hook, "", cta_line, "#IELTS #pielts"]
    full = "\n".join(parts)
    if len(full) <= 280:
        return full

    # Trim hook
    max_hook = 280 - len(cta_line) - len("#IELTS #pielts") - 4
    return f"{hook[:max_hook]}…\n\n{cta_line}\n#IELTS #pielts"

"""
Social Media Dashboard — live stats + monetization progress for all platforms.
Pulls: YouTube, Instagram, Facebook, TikTok, Twitter/X, LinkedIn.
Shows progress toward each platform's monetization threshold.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import httpx

from .. import config

_API = "https://graph.facebook.com/v19.0"
_CONN = config.ROOT / "data" / "connections.json"


def _conn() -> dict:
    try:
        return json.loads(_CONN.read_text())
    except Exception:
        return {}


# ── Per-platform fetchers ─────────────────────────────────────────────────────

def _youtube() -> dict:
    try:
        from .. import pielts
        s = pielts.yt_stats() or {}
        subs  = s.get("subscribers", 0) or 0
        views = s.get("views", 0) or 0
        vids  = s.get("video_count", 0) or 0

        # Shorts monetization: 1000 subs + 10M Shorts views (90 days)
        # Standard: 1000 subs + 4000 watch hours
        subs_pct  = min(100, round(int(str(subs).replace(",","")) / 1000 * 100))
        views_pct = min(100, round(int(str(views).replace(",","")) / 10_000_000 * 100))

        return {
            "connected": True,
            "handle": "@pieltsapp",
            "subscribers": subs,
            "total_views": views,
            "videos": vids,
            "monetization": {
                "program": "YouTube Partner Program (Shorts)",
                "threshold": {"subscribers": 1000, "shorts_views_90d": "10M"},
                "progress": {
                    "subscribers_pct": subs_pct,
                    "views_pct": views_pct,
                },
                "unlocked": subs_pct >= 100 and views_pct >= 100,
            }
        }
    except Exception as e:
        return {"connected": False, "error": str(e)[:100]}


def _instagram() -> dict:
    c = _conn()
    token = c.get("facebook", {}).get("page_access_token", "")
    ig_id = c.get("instagram", {}).get("ig_account_id", "")
    if not token or not ig_id:
        return {"connected": False, "error": "not configured"}
    try:
        r = httpx.get(f"{_API}/{ig_id}", params={
            "fields": "followers_count,media_count,name,username",
            "access_token": token
        }, timeout=15)
        d = r.json()
        followers = d.get("followers_count", 0)
        # IG Reels Bonus: 10k followers (invite-only)
        pct = min(100, round(followers / 10_000 * 100))
        return {
            "connected": True,
            "handle": f"@{d.get('username', 'pieltsapp')}",
            "followers": followers,
            "posts": d.get("media_count", 0),
            "monetization": {
                "program": "Instagram Reels Bonus (invite-only after 10K)",
                "threshold": {"followers": 10_000},
                "progress": {"followers_pct": pct},
                "unlocked": pct >= 100,
            }
        }
    except Exception as e:
        return {"connected": False, "error": str(e)[:100]}


def _facebook() -> dict:
    c = _conn()
    token   = c.get("facebook", {}).get("page_access_token", "")
    page_id = c.get("facebook", {}).get("page_id", "")
    if not token or not page_id:
        return {"connected": False, "error": "not configured"}
    try:
        r = httpx.get(f"{_API}/{page_id}", params={
            "fields": "fan_count,followers_count,name",
            "access_token": token
        }, timeout=15)
        d = r.json()
        followers = d.get("followers_count", 0) or d.get("fan_count", 0)
        # FB In-Stream Ads: 10K followers + 600K mins viewed (60d)
        pct = min(100, round(followers / 10_000 * 100))
        return {
            "connected": True,
            "handle": d.get("name", "pielts"),
            "followers": followers,
            "page_likes": d.get("fan_count", 0),
            "monetization": {
                "program": "Facebook In-Stream Ads",
                "threshold": {"followers": 10_000, "minutes_viewed_60d": 600_000},
                "progress": {"followers_pct": pct},
                "unlocked": False,
                "note": "Also need 600K minutes viewed in 60 days",
            }
        }
    except Exception as e:
        return {"connected": False, "error": str(e)[:100]}


def _tiktok() -> dict:
    c = _conn().get("tiktok", {})
    token   = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    open_id = os.getenv("TIKTOK_OPEN_ID", "")

    if not token or not open_id:
        app_review = c.get("connected", False)
        return {
            "connected": False,
            "handle": c.get("handle", "@pieltsapp"),
            "status": "App in review — connect after approval",
            "monetization": {
                "program": "TikTok Creator Fund",
                "threshold": {"followers": 10_000, "views_30d": 100_000},
                "progress": {"followers_pct": 0, "views_pct": 0},
                "unlocked": False,
            }
        }
    try:
        r = httpx.post(
            "https://open.tiktokapis.com/v2/user/info/",
            headers={"Authorization": f"Bearer {token}"},
            json={"fields": ["follower_count", "following_count", "video_count", "display_name"]},
            timeout=15,
        )
        if r.status_code == 404 or (r.status_code != 200 and not r.text.strip()):
            # Sandbox tokens don't support user info endpoint — but posting still works
            return {
                "connected": True,
                "handle": c.get("handle", "@pieltsapp"),
                "status": "connected (sandbox) — posting enabled",
                "monetization": {
                    "program": "TikTok Creator Fund",
                    "threshold": {"followers": 10_000, "views_30d": 100_000},
                    "progress": {"followers_pct": 0},
                    "unlocked": False,
                }
            }
        if r.status_code != 200:
            return {
                "connected": True,
                "handle": c.get("handle", "@pieltsapp"),
                "status": "token_expired — re-auth needed",
                "monetization": {
                    "program": "TikTok Creator Fund",
                    "threshold": {"followers": 10_000, "views_30d": 100_000},
                    "progress": {"followers_pct": 0},
                    "unlocked": False,
                }
            }
        d = r.json().get("data", {}).get("user", {})
        followers = d.get("follower_count", 0)
        f_pct = min(100, round(followers / 10_000 * 100))
        return {
            "connected": True,
            "handle": f"@{d.get('display_name', 'pieltsapp')}",
            "followers": followers,
            "videos": d.get("video_count", 0),
            "monetization": {
                "program": "TikTok Creator Fund",
                "threshold": {"followers": 10_000, "views_30d": 100_000},
                "progress": {"followers_pct": f_pct},
                "unlocked": False,
            }
        }
    except Exception as e:
        return {"connected": True, "handle": c.get("handle", "@pieltsapp"),
                "status": "token_expired — re-auth needed", "error": str(e)[:100]}


def _twitter() -> dict:
    c = _conn().get("x", {})
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "")
    api_key      = os.getenv("TWITTER_API_KEY", "")
    if not bearer_token and not api_key:
        return {"connected": False, "handle": c.get("handle", "@pieltsofficial"), "error": "not configured"}
    try:
        import tweepy
        # Use OAuth 1.0a for stats (get_me); bearer token as fallback for read-only lookup
        acc_token  = os.getenv("TWITTER_ACCESS_TOKEN", "")
        acc_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")
        if acc_token and acc_secret:
            client = tweepy.Client(
                consumer_key=api_key, consumer_secret=os.getenv("TWITTER_API_SECRET",""),
                access_token=acc_token, access_token_secret=acc_secret,
            )
            me = client.get_me(user_fields=["public_metrics"])
        else:
            client = tweepy.Client(bearer_token=bearer_token)
            handle = c.get("handle", "@pieltsofficial").lstrip("@")
            me = client.get_user(username=handle, user_fields=["public_metrics"])
        metrics = me.data.public_metrics if (me and me.data) else {}
        followers = metrics.get("followers_count", 0)
        f_pct = min(100, round(followers / 10_000 * 100))
        return {
            "connected": True,
            "handle": f"@{me.data.username}" if (me and me.data) else c.get("handle", "@pieltsofficial"),
            "followers": followers,
            "tweets": metrics.get("tweet_count", 0),
            "monetization": {
                "program": "X Ads Revenue Share (500 followers + 5M impressions/month)",
                "threshold": {"followers": 500, "impressions_30d": 5_000_000},
                "progress": {"followers_pct": min(100, round(followers / 500 * 100))},
                "unlocked": followers >= 500,
            }
        }
    except tweepy.Unauthorized:
        return {"connected": True, "handle": c.get("handle", "@pieltsofficial"),
                "status": "token_invalid — regenerate in X Developer Console",
                "monetization": {"program": "X Ads Revenue Share", "threshold": {"followers": 500},
                                  "progress": {"followers_pct": 0}, "unlocked": False}}
    except Exception as e:
        return {"connected": True, "handle": c.get("handle", "@pieltsofficial"), "error": str(e)[:100]}


def _linkedin() -> dict:
    c = _conn().get("linkedin", {})
    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    if not token:
        return {"connected": False, "handle": "pielts", "error": "not configured"}
    try:
        r = httpx.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        d = r.json()
        name = d.get("name", "Ajay Chaulagain")
        return {
            "connected": True,
            "handle": name,
            "status": "personal profile — posting enabled",
            "monetization": {
                "program": "LinkedIn Newsletter / Creator Mode",
                "threshold": {"followers": 1_000},
                "progress": {"followers_pct": 0},
                "unlocked": False,
                "note": "Follower count not exposed by LinkedIn API",
            }
        }
    except Exception as e:
        return {"connected": False, "handle": "pielts", "error": str(e)[:100]}


# ── Main dashboard ────────────────────────────────────────────────────────────

def get_dashboard() -> dict:
    """Pull live stats from all 6 platforms + monetization progress."""
    yt = _youtube()
    ig = _instagram()
    fb = _facebook()
    tt = _tiktok()
    tw = _twitter()
    li = _linkedin()

    # Overall monetization summary
    platforms_unlocked = sum([
        yt.get("monetization", {}).get("unlocked", False),
        ig.get("monetization", {}).get("unlocked", False),
        fb.get("monetization", {}).get("unlocked", False),
        tt.get("monetization", {}).get("unlocked", False),
        tw.get("monetization", {}).get("unlocked", False),
        li.get("monetization", {}).get("unlocked", False),
    ])

    tt_followers = tt.get("followers", "—")

    # Quick Telegram-friendly text summary
    lines = [
        f"📊 MR. YETI — SOCIAL DASHBOARD ({datetime.now().strftime('%d %b %Y %H:%M')})",
        "",
        f"▶️  YouTube @pieltsapp",
        f"   Subs: {yt.get('subscribers', 'N/A')} / 1,000  •  Views: {yt.get('total_views', 'N/A')}",
        f"   Monetized: {'✅ YES' if yt.get('monetization',{}).get('unlocked') else '⏳ No'}",
        "",
        f"📸 Instagram {ig.get('handle','@pieltsofficial')}",
        f"   Followers: {ig.get('followers', 'N/A')} / 10,000",
        f"   Monetized: {'✅ YES' if ig.get('monetization',{}).get('unlocked') else '⏳ No'}",
        "",
        f"📘 Facebook {fb.get('handle','pielts')}",
        f"   Followers: {fb.get('followers', 'N/A')} / 10,000",
        f"   Monetized: {'✅ YES' if fb.get('monetization',{}).get('unlocked') else '⏳ No'}",
        "",
        f"🎵 TikTok {tt.get('handle','@pieltsapp')}",
        f"   Status: {tt.get('status', f'Followers: {tt_followers} / 10,000')}",
        f"   Monetized: {'✅ YES' if tt.get('monetization',{}).get('unlocked') else '⏳ No'}",
        "",
        f"🐦 X/Twitter {tw.get('handle','@pieltsofficial')}",
        f"   Followers: {tw.get('followers', tw.get('error', 'N/A'))} / 500",
        f"   Monetized: {'✅ YES' if tw.get('monetization',{}).get('unlocked') else '⏳ No'}",
        "",
        f"💼 LinkedIn {li.get('handle','Ajay Chaulagain')}",
        f"   Status: {li.get('status', li.get('error', 'N/A'))}",
        f"   Monetized: {'✅ YES' if li.get('monetization',{}).get('unlocked') else '⏳ No'}",
        "",
        f"💰 Platforms monetized: {platforms_unlocked}/6",
    ]

    return {
        "ok": True,
        "fetched_at": datetime.now().isoformat(),
        "youtube": yt,
        "instagram": ig,
        "facebook": fb,
        "tiktok": tt,
        "twitter": tw,
        "linkedin": li,
        "summary": "\n".join(lines),
        "platforms_monetized": platforms_unlocked,
    }

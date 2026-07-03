"""Content Factory — the autonomous content production line (M3 Phase B).

Everything after Analytics already exists (Discovery gate, episode recording,
Learning Runtime). This wires the production side: one content item flows
through the Discovery gate and out to real platform posters, and every publish
becomes a platform Episode the Learning Runtime improves from.

    content → Discovery gate → real poster (FB/IG/TikTok/X/LinkedIn/YouTube)
            → Episode → Learning Runtime → better future content

The poster dispatcher adapts a standard content dict to each platform's real
function; adapters are lazily imported and guarded so an unconfigured platform
returns a clean error instead of crashing the line. Injectable for tests (AP-12).
"""
from __future__ import annotations

from typing import Callable

from saathi.publishing_pipeline import PublishingPipeline, PublishResult, default_discovery_checks


def _adapter_facebook(content: dict) -> dict:
    from saathi.tools import meta_post
    return meta_post.post_facebook(content.get("description", ""), content.get("link", ""))


def _adapter_instagram(content: dict) -> dict:
    from saathi.tools import meta_post
    thumb = content.get("thumbnail")
    cap = content.get("description", "")
    if thumb:
        return meta_post.post_instagram_image_local(thumb, cap)
    return meta_post.post_instagram_text(cap)


def _adapter_twitter(content: dict) -> dict:
    from saathi.tools import twitter_post
    text = content.get("title", "")
    thumb = content.get("thumbnail")
    return twitter_post.tweet_with_image(text, thumb) if thumb else twitter_post.tweet(text)


def _adapter_linkedin(content: dict) -> dict:
    from saathi.tools import linkedin_post
    fn = getattr(linkedin_post, "post_text", None) or getattr(linkedin_post, "post", None)
    if fn is None:
        return {"error": "linkedin poster not available"}
    return fn(content.get("description", "") or content.get("title", ""))


# platform → real adapter. YouTube/TikTok go through existing pipelines elsewhere;
# here we cover the connectors with simple text/image posting.
_ADAPTERS: dict[str, Callable[[dict], dict]] = {
    "facebook": _adapter_facebook,
    "instagram": _adapter_instagram,
    "twitter": _adapter_twitter,
    "x": _adapter_twitter,
    "linkedin": _adapter_linkedin,
}


def default_poster(content: dict, platform: str) -> dict:
    """Dispatch to the real platform poster; guarded so one bad platform can't
    take down the line."""
    adapter = _ADAPTERS.get(platform.lower())
    if adapter is None:
        return {"error": f"no connector for platform {platform!r}"}
    try:
        return adapter(content)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


class ContentFactory:
    def __init__(self, poster: Callable[[dict, str], dict] = default_poster,
                 record_episode: Callable[..., int] | None = None,
                 publish_event: "Callable[[str, dict], None] | None" = None):
        if record_episode is None or publish_event is None:
            # production wiring: episodes → Learning Runtime, events → Event Fabric
            self.pipeline = PublishingPipeline.production(publisher=poster)
        else:
            self.pipeline = PublishingPipeline(
                publisher=poster, discovery=default_discovery_checks,
                record_episode=record_episode, publish_event=publish_event)

    def publish(self, content: dict, platforms: list[str],
                product: str = "mr_yeti") -> dict[str, PublishResult]:
        """Publish one content item to several platforms, each gated by Discovery."""
        return {p: self.pipeline.publish(content, platform=p, product=product)
                for p in platforms}

    def record_analytics(self, *, product: str, platform: str, content_id: str,
                         views: int, likes: int) -> int:
        return self.pipeline.record_performance(
            product=product, platform=platform, content_id=content_id,
            views=views, likes=likes)

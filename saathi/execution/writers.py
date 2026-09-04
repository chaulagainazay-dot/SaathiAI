"""The registry of external writers, and the one way to reach them.

Phase 19 put a guard in front of every external mutation, so nothing writes
outside governed execution. Phase 20 proved a legitimate scheduled write can pass
through. What was missing between them is this: a way for a caller to *ask* for
one of those writes and have it routed through the gateway, rather than every
caller assembling a ToolIntent by hand and hoping it matches.

So this is deliberately not new authority. It is a lookup table plus a dispatch
function. Everything that decides anything already exists:

    ExecutionGateway / UniversalBoundary   decides
    the boundary's handler dispatch        opens the Phase 19 grant
    the guarded writer function            performs the side effect
    Phase 17 sanitisation                  cleans what comes back

The registry's value is that it is a *closed list*. A writer not in it cannot be
reached through this path, and a writer in it can only be reached with a
ToolIntent the boundary admitted. Adding one is a deliberate edit, which is the
property a scattered set of ad-hoc call sites did not have.

**Nothing here starts sending.** Registering a writer makes it reachable under
authority; it does not schedule anything, does not re-enable any scheduler job,
and does not lower any gate. A registered writer with no delegation, no approval
and no connector authority refuses exactly as it did before.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Writer:
    """One external mutation the system knows how to perform under authority.

    `module` and `func` are resolved lazily at dispatch. Importing a dozen
    provider modules at registry-import time would be an import-time cost for
    callers that use one of them, and Phase 15 spent a milestone removing
    import-time side effects.
    """

    key: str
    #: The connector-platform tool this maps to, where one is registered. Its
    #: `ToolDef` is what carries risk class, approval requirement and mutation
    #: class -- this registry does not restate any of them, because a second
    #: copy of an authority fact is a second thing to keep in sync.
    tool_id: str
    module: str
    func: str
    #: The target string the writer passes to the Phase 19 guard. Recorded so a
    #: mismatch between what is registered and what is guarded is visible.
    egress_target: str

    def resolve(self):
        import importlib

        return getattr(importlib.import_module(self.module), self.func)


def _w(key, tool_id, module, func, egress_target) -> Writer:
    return Writer(key=key, tool_id=tool_id, module=module, func=func,
                  egress_target=egress_target)


#: Every external writer, keyed by a stable name. Closed by construction: a
#: mutation reachable through this path is one somebody added here on purpose.
#:
#: Grouped by family rather than by module, because the authority questions are
#: per family -- a Telegram send and a Gmail send differ in connector, not in
#: kind, while a paid generation call differs in kind from both.
WRITERS: dict[str, Writer] = {w.key: w for w in (
    # ── messaging ──────────────────────────────────────────────────────────
    _w("telegram.send", "telegram.send_message",
       "saathi.connectors.adapters.telegram", "TelegramAdapter", "telegram.send_message"),

    # ── email ──────────────────────────────────────────────────────────────
    _w("gmail.send", "gmail.send_email",
       "saathi.tools.email_tool", "send_email", "gmail.send"),
    _w("smtp.send", "", "saathi.mailer", "send", "smtp.send"),
    _w("mailerlite.subscriber", "", "saathi.tools.mailerlite", "add_subscriber",
       "mailerlite.subscribers"),
    _w("mailerlite.group", "", "saathi.tools.mailerlite", "create_group",
       "mailerlite.groups"),
    _w("mailerlite.campaign", "", "saathi.tools.mailerlite", "create_campaign",
       "mailerlite.campaigns"),

    # ── social ─────────────────────────────────────────────────────────────
    _w("facebook.post", "", "saathi.tools.meta_post", "post_facebook",
       "facebook.page.feed"),
    _w("facebook.video", "", "saathi.tools.mr_yeti_pipeline", "_upload_facebook_video",
       "facebook.videos"),
    _w("instagram.text", "", "saathi.tools.meta_post", "post_instagram_text",
       "instagram.media"),
    _w("instagram.image", "", "saathi.tools.meta_post", "post_instagram_image",
       "instagram.media"),
    _w("instagram.reel", "", "saathi.tools.meta_post", "post_instagram_reel",
       "instagram.media"),
    _w("twitter.tweet", "", "saathi.tools.twitter_post", "tweet", "twitter.tweet"),
    _w("linkedin.post", "", "saathi.tools.linkedin_post", "post_text",
       "linkedin.share"),
    _w("tiktok.publish", "", "saathi.tools.tiktok_post", "post_video",
       "tiktok.video_publish"),
    _w("reddit.reply", "", "saathi.tools.reddit_outreach", "send_reply",
       "reddit.comment"),
    _w("n8n.social", "", "saathi.tools.content", "post", "n8n.social_post"),
    _w("youtube.publish", "", "saathi.tools.content_studio", "publish_to_youtube",
       "youtube.publish"),

    # ── paid generation ────────────────────────────────────────────────────
    # External by the Phase 19 definition: each creates a remote job and spends
    # the operator's quota, whether or not anything is published.
    _w("gen.video.runway", "", "saathi.tools.backup_video", "generate_runway",
       "runway.image_to_video"),
    _w("gen.video.kling", "", "saathi.tools.backup_video", "generate_kling",
       "kling.text2video"),
    _w("gen.video.minimax", "", "saathi.tools.backup_video", "generate_minimax",
       "minimax.video_generation"),
    _w("gen.video.pika", "", "saathi.tools.backup_video", "generate_pika",
       "pika.generate"),
    _w("gen.avatar.heygen", "", "saathi.tools.content_studio", "make_animated_video",
       "heygen.video"),
    _w("gen.avatar.did", "", "saathi.tools.content_studio", "make_avatar_video",
       "d_id.talks"),
    _w("gen.voice.elevenlabs", "", "saathi.tools.content_studio",
       "elevenlabs_voiceover", "elevenlabs.tts"),
    _w("gen.image.flux", "", "saathi.tools.images", "_flux", "flux.image_generate"),
    _w("gen.speech.openai", "", "saathi.tools.voice", "_openai", "openai.tts"),
    _w("gen.transcribe.openai", "", "saathi.tools.video_editor", "transcribe_audio",
       "openai.transcriptions"),
    _w("gen.transcribe.gemini", "", "saathi.tools.speaking_eval", "_transcribe",
       "gemini.transcribe"),
)}


class UnknownWriter(KeyError):
    """Asked for a writer that is not in the closed registry."""


def get(key: str) -> Writer:
    try:
        return WRITERS[key]
    except KeyError:
        raise UnknownWriter(key) from None


def handler_for(key: str, args: dict):
    """A boundary handler that performs one registered write.

    Returned rather than called: the boundary invokes it *after* authorization,
    inside the grant it opens. That ordering is the whole point -- the writer
    cannot run unless the boundary decided it may, and the guard inside the
    writer refuses if it is somehow reached any other way.
    """
    writer = get(key)

    def _handler(intent, rec):
        target = writer.resolve()
        # Adapter classes expose the verb as a method; plain functions are
        # called directly. Both end at a Phase 19 guard.
        if isinstance(target, type):
            result = target().send(args.get("account", {}), args.get("params", {}))
        else:
            result = target(**args)
        from saathi.execution.sanitization import sanitize

        cleaned, report = sanitize(result)
        return {"status": "succeeded",
                "summary": f"{key} sanitized={not report.failed}",
                "result": None if report.failed else cleaned}

    return _handler

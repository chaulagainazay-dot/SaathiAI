"""Prose cleaner — removes AI writing tells using stop-slop rules.

Based on https://github.com/hardikpandya/stop-slop (MIT License, Hardik Pandya)
Useful as a post-processor for any Mr. Yeti content or MailerLite email copy.
"""
from __future__ import annotations
# LLM calls route through the Model Router (infrastructure.llm), not the SDK.
import os

_STOP_SLOP_SYSTEM = """\
You are an expert prose editor. Your only job is to remove AI writing patterns from text.

Apply these rules strictly:

1. CUT filler phrases: remove throat-clearing openers, emphasis crutches ("truly", "certainly",
   "absolutely"), and all adverbs ending in -ly.

2. BREAK formulaic structures: no binary contrasts ("not X, but Y"), no negative listings,
   no dramatic one-line fragments, no rhetorical setup sentences, no false agency
   ("the complaint becomes a fix").

3. USE active voice: every sentence needs a human subject doing something. No passive.
   No inanimate objects doing human things ("the decision emerges").

4. BE specific: no vague declaratives ("The reasons are structural" → name the reasons).
   No lazy extremes ("every", "always", "never") doing vague work.

5. PUT the reader in the room: use "you" not "people". Specifics beat abstractions.

6. VARY rhythm: mix sentence lengths. Two items beat three. End paragraphs differently.
   No em dashes.

7. TRUST readers: state facts directly. Skip softening, justification, hand-holding.

8. CUT quotables: if it sounds like a pull-quote, rewrite it.

Quick checks before returning:
- Any adverbs? Kill them.
- Any passive voice? Find the actor, make them subject.
- Inanimate thing doing a human verb? Name the person.
- Sentence starts with Wh- word? Restructure.
- "here's what/this/that" throat-clearing? Cut to the point.
- "not X, it's Y" contrast? State Y directly.
- Three consecutive same-length sentences? Break one.
- Em-dash anywhere? Remove it.
- Vague declarative? Name the specific thing.

Return ONLY the cleaned text. No commentary, no score, no explanation.
"""


def clean_prose(text: str, context: str = "") -> dict:
    """Remove AI writing tells from text using stop-slop rules.

    Args:
        text: The prose to clean (email copy, blog post, social post, etc.)
        context: Optional context hint — e.g. "ielts email", "facebook post", "blog intro"

    M20.3: opt-in governed local path via ``saathi.inference.compat`` when rollout
    mode is not ``legacy``. Default remains legacy ``llm.generate``.
    """
    # Legacy path historically required Anthropic key presence; keep that gate only
    # for pure-legacy so local rollout can work without cloud keys.
    from saathi.inference.caller_rollout import CALLER_PROSE_CLEAN, InfRolloutMode, resolve_mode

    mode = resolve_mode(CALLER_PROSE_CLEAN)
    if mode == InfRolloutMode.LEGACY:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            # Still allow injected/router path if other providers exist via llm.generate
            pass

    try:
        from saathi.inference.compat import prose_clean_adopted
        from saathi.infrastructure.llm import generate
        from saathi.infrastructure.model_router import ModelLabel

        def _legacy(**kwargs):
            return generate(
                kwargs.get("label", ModelLabel.STANDARD),
                kwargs["prompt"],
                system=kwargs.get("system", _STOP_SLOP_SYSTEM),
                prefer=kwargs.get("prefer"),
                max_tokens=min(int(kwargs.get("max_tokens") or 1024), 1024),
                timeout=int(kwargs.get("timeout") or 60),
            )

        return prose_clean_adopted(
            text, context=context, system=_STOP_SLOP_SYSTEM, legacy_fn=_legacy,
        )
    except Exception as e:
        return {"error": type(e).__name__, "message": str(e)[:300]}


def score_prose(text: str) -> dict:
    """Score prose on stop-slop dimensions: Directness, Rhythm, Trust, Authenticity, Density.
    Returns scores out of 10 each (50 total). Below 35 means revise.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set"}

    score_prompt = f"""\
Score this text on each dimension (1-10 each). Reply with ONLY a JSON object, nothing else.

Dimensions:
- directness: statements vs announcements?
- rhythm: varied vs metronomic?
- trust: respects reader intelligence?
- authenticity: sounds human?
- density: anything cuttable?

Text to score:
{text}

Reply format: {{"directness": N, "rhythm": N, "trust": N, "authenticity": N, "density": N, "total": N, "verdict": "pass|revise"}}
"""
    try:
        from saathi.infrastructure.llm import generate
        from saathi.infrastructure.model_router import ModelLabel
        import json
        out = generate(ModelLabel.STANDARD, score_prompt,
                       "Reply with ONLY a JSON object.", max_tokens=256).text.strip()
        return json.loads(out)
    except Exception as e:
        return {"error": type(e).__name__, "message": str(e)[:300]}

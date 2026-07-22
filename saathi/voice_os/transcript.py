"""M12 transcript pipeline: raw → partial → final → normalized → command.

Only one final user message is submitted to ChatEngine per completed voice
turn — partial transcripts update in-memory/UI state only, never persisted as
separate chat messages.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


def normalize(text: str) -> str:
    """Whitespace cleanup + punctuation normalization."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if t and t[-1] not in ".!?":
        pass  # do not force punctuation — voice input is often fragmentary
    return t


def dedupe_fragments(fragments: list[str]) -> str:
    """Streaming STT often re-sends growing prefixes of the same utterance
    ("hello", "hello there", "hello there friend"). Keep only the longest
    fragment that is a superset (by prefix) of the others, concatenating
    genuinely distinct trailing fragments."""
    if not fragments:
        return ""
    cleaned = [normalize(f) for f in fragments if normalize(f)]
    if not cleaned:
        return ""
    out = [cleaned[0]]
    for frag in cleaned[1:]:
        prev = out[-1]
        if frag.startswith(prev):
            out[-1] = frag           # growing prefix — replace
        elif prev.startswith(frag):
            continue                 # shorter duplicate — skip
        else:
            out.append(frag)         # genuinely new content
    return " ".join(out).strip()


# ── voice command recognition (bounded, local, confidence-gated) ──────────
_COMMANDS: dict[str, tuple[str, ...]] = {
    "stop": ("stop", "stop talking", "shut up"),
    "pause": ("pause",),
    "resume": ("resume", "continue"),
    "repeat": ("repeat", "say that again", "what did you say"),
    "cancel": ("cancel", "cancel that", "never mind"),
    "approve": ("approve", "yes approve", "approve it", "approve that"),
    "deny": ("deny", "reject", "no deny", "deny it"),
    "mute": ("mute", "mute yourself"),
    "unmute": ("unmute",),
    "solo_mode": ("switch to solo", "solo mode", "use solo"),
    "team_mode": ("switch to team", "team mode", "use team"),
    "new_conversation": ("new conversation", "start a new conversation", "new chat"),
    "summarize": ("summarize this conversation", "summarize", "give me a summary"),
    "status": ("what is happening", "what's happening", "status update"),
}


@dataclass
class CommandMatch:
    command: str
    confidence: float
    matched_phrase: str


def detect_command(text: str, *, min_confidence: float = 0.75) -> CommandMatch | None:
    """Exact/near-exact phrase match only — never fuzzy-triggers destructive
    or approval commands from loose keyword overlap."""
    t = normalize(text).lower().strip(" .!?")
    if not t:
        return None
    for cmd, phrases in _COMMANDS.items():
        for phrase in phrases:
            if t == phrase:
                return CommandMatch(command=cmd, confidence=1.0, matched_phrase=phrase)
    # allow a short leading/trailing filler ("saathi, stop" / "please stop")
    for cmd, phrases in _COMMANDS.items():
        for phrase in phrases:
            if t.endswith(phrase) and len(t) - len(phrase) <= 12:
                conf = 0.8
                if conf >= min_confidence:
                    return CommandMatch(command=cmd, confidence=conf, matched_phrase=phrase)
    return None


AGENT_NAMES = ("planner", "researcher", "architect", "builder", "reviewer",
              "executor", "writer", "ceo")


def detect_agent_switch(text: str) -> str | None:
    t = normalize(text).lower()
    m = re.match(r"^(use|switch to)\s+(the\s+)?(\w+)", t)
    if m and m.group(3) in AGENT_NAMES:
        return m.group(3)
    return None

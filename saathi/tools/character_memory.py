"""Character memory for Mr. Yeti — tracks recurring fictional IELTS students across episodes.

Enables storyline continuity like "Remember Rahul from episode 5? He made the same mistake again!"
to drive binge-watching behaviour.
"""

import json
import random
from pathlib import Path
from typing import Optional

from .. import config
from ._llm_helper import ask_llm, extract_json

MEMORY_PATH = config.ROOT / "data" / "character_memory.json"

DEFAULT_CHARACTERS = [
    {
        "name": "Rahul",
        "nationality": "Indian",
        "current_band": "5.5",
        "target_band": "7.0",
        "recurring_mistake": "overuses 'basically' and 'actually' in Speaking",
        "personality": "hardworking but nervous",
        "episodes_appeared": 0,
        "last_seen_episode": None,
        "episode_history": [],
    },
    {
        "name": "Sarah",
        "nationality": "Korean",
        "current_band": "6.0",
        "target_band": "7.5",
        "recurring_mistake": "writes task 1 and task 2 in wrong time allocation",
        "personality": "perfectionist, gets frustrated",
        "episodes_appeared": 0,
        "last_seen_episode": None,
        "episode_history": [],
    },
    {
        "name": "Diego",
        "nationality": "Brazilian",
        "current_band": "5.0",
        "target_band": "6.5",
        "recurring_mistake": "translates Portuguese phrases literally into English",
        "personality": "funny and self-deprecating",
        "episodes_appeared": 0,
        "last_seen_episode": None,
        "episode_history": [],
    },
    {
        "name": "Fatima",
        "nationality": "Saudi",
        "current_band": "6.5",
        "target_band": "7.5",
        "recurring_mistake": "excellent grammar but monotone Speaking, no discourse markers",
        "personality": "confident but needs warmth",
        "episodes_appeared": 0,
        "last_seen_episode": None,
        "episode_history": [],
    },
]


def load_memory() -> dict:
    """Return full memory dict with keys: characters, storylines, episode_count."""
    if not MEMORY_PATH.exists():
        data = {
            "characters": {c["name"]: c for c in DEFAULT_CHARACTERS},
            "storylines": [],
            "episode_count": 0,
        }
        save_memory(data)
        return data
    return json.loads(MEMORY_PATH.read_text())


def save_memory(data: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(data, indent=2))


def get_or_create_character(name: str) -> dict:
    """Return character dict; creates a blank entry if unknown."""
    data = load_memory()
    if name not in data["characters"]:
        data["characters"][name] = {
            "name": name,
            "nationality": "Unknown",
            "current_band": "5.0",
            "target_band": "7.0",
            "recurring_mistake": "not yet identified",
            "personality": "not yet defined",
            "episodes_appeared": 0,
            "last_seen_episode": None,
            "episode_history": [],
        }
        save_memory(data)
    return data["characters"][name]


def update_character(
    name: str,
    episode_slug: str,
    band_score: Optional[str] = None,
    event: Optional[str] = None,
) -> None:
    """Update character stats after an episode."""
    data = load_memory()
    char = data["characters"].setdefault(name, get_or_create_character(name))
    char["episodes_appeared"] = char.get("episodes_appeared", 0) + 1
    char["last_seen_episode"] = episode_slug
    history = char.setdefault("episode_history", [])
    entry = {"episode": episode_slug}
    if band_score:
        char["current_band"] = band_score
        entry["band_score"] = band_score
    if event:
        entry["event"] = event
    history.append(entry)
    data["characters"][name] = char
    save_memory(data)


def get_active_characters() -> list[dict]:
    """Characters who appeared in the last 10 episodes — good to reference."""
    data = load_memory()
    episode_count = data.get("episode_count", 0)
    cutoff = episode_count - 10

    active = []
    for char in data["characters"].values():
        history = char.get("episode_history", [])
        if not history:
            # Never appeared — include defaults so new shows still have characters
            if char.get("episodes_appeared", 0) == 0:
                continue
        # Check if any appearance is recent
        for entry in history[-3:]:  # check last few entries
            ep_slug = entry.get("episode")
            # If we can't determine recency by number, include all who appeared
            if char.get("episodes_appeared", 0) > 0:
                active.append(char)
                break
    return active


def get_character_context_for_script(n_characters: int = 2) -> str:
    """Return a paragraph for the script prompt listing recurring students."""
    data = load_memory()
    all_chars = list(data["characters"].values())

    # Prefer characters who've appeared before; fall back to defaults
    appeared = [c for c in all_chars if c.get("episodes_appeared", 0) > 0]
    never = [c for c in all_chars if c.get("episodes_appeared", 0) == 0]

    pool = appeared if len(appeared) >= n_characters else appeared + never
    selected = pool[:n_characters]

    if not selected:
        return ""

    lines = []
    for c in selected:
        times = c.get("episodes_appeared", 0)
        times_str = f"appeared {times} time{'s' if times != 1 else ''}"
        lines.append(
            f"  - {c['name']} (Band {c['current_band']}, from {c['nationality']}, "
            f"{c['recurring_mistake']}, {times_str})"
        )

    char_list = "\n".join(lines)
    return (
        f"Mr. Yeti has these recurring students:\n{char_list}\n"
        f"Reference at least one of them naturally in this episode."
    )


def generate_new_character(nationality: Optional[str] = None) -> dict:
    """Use LLM to create a new realistic student character."""
    nationality_hint = f'from {nationality}' if nationality else 'from any country'
    prompt = f"""Create a new fictional IELTS student character {nationality_hint} for Mr. Yeti's channel.
Return ONLY valid JSON with these fields:
{{
  "name": "string",
  "nationality": "string",
  "current_band": "number as string e.g. 5.5",
  "target_band": "number as string e.g. 7.0",
  "recurring_mistake": "one specific IELTS mistake this student always makes",
  "personality": "2-3 word personality description",
  "episodes_appeared": 0,
  "last_seen_episode": null,
  "episode_history": []
}}"""
    raw = ask_llm(prompt)
    char = extract_json(raw)
    if not char or "name" not in char:
        # Fallback to a simple generated character
        char = {
            "name": f"Student_{random.randint(100, 999)}",
            "nationality": nationality or "Unknown",
            "current_band": "5.5",
            "target_band": "7.0",
            "recurring_mistake": "struggles with coherence in Writing Task 2",
            "personality": "eager but inconsistent",
            "episodes_appeared": 0,
            "last_seen_episode": None,
            "episode_history": [],
        }
    data = load_memory()
    data["characters"][char["name"]] = char
    save_memory(data)
    return char


def record_episode_characters(episode_slug: str, characters_mentioned: list[str]) -> None:
    """Called after script generation to record who appeared in the episode."""
    data = load_memory()
    data["episode_count"] = data.get("episode_count", 0) + 1
    save_memory(data)
    for name in characters_mentioned:
        update_character(name, episode_slug)


def get_storyline_hook(character_name: str) -> str:
    """Return a callback line referencing a character's journey."""
    char = get_or_create_character(character_name)
    times = char.get("episodes_appeared", 0)
    mistake = char.get("recurring_mistake", "the same mistake")
    band = char.get("current_band", "?")

    if times == 0:
        return f"Meet {character_name} — a new student joining Mr. Yeti's class today!"
    elif times == 1:
        return (
            f"Remember {character_name} from last time? "
            f"They're back — and still {mistake}!"
        )
    else:
        return (
            f"Remember {character_name}? They've appeared {times} times now, "
            f"currently at Band {band} — and they just {mistake} again!"
        )

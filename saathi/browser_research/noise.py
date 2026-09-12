"""Phase 5 — deterministic interface-noise filtering.

Removes navigation, headers, footers, social/login/language/accessibility, phone
and email interface lines, copyright, and breadcrumbs. Does NOT drop meaningful
financial disclosure text. Pure and testable.
"""
from __future__ import annotations

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?i)(phone|tel|fax|mobile|ext\b|\+977|977[\s-]?1)")
_COPYRIGHT = re.compile(r"(?i)(©|copyright|all rights reserved|powered by|designed by)")
_NAVWORD = re.compile(
    r"(?i)^(home|about|contact|contact us|login|log in|register|sign in|sign up|search|menu|"
    r"skip to (main )?content|toggle navigation|breadcrumb|sitemap|faq|faqs|downloads|gallery|"
    r"careers?|tenders?|feedback|newsletter|subscribe|follow us|share|print|back to top|read more|"
    r"english|nepali|नेपाली|language|accessibility|screen reader|font size|dark mode)$"
)
_SOCIAL = re.compile(r"(?i)\b(facebook|twitter|x\.com|instagram|linkedin|youtube|tiktok|whatsapp|viber)\b")
_ADDRESS = re.compile(r"(?i)(p\.?o\.? box|kathmandu, nepal|thapathali|baluwatar|new baneshwor)")
_MENU_SEP = re.compile(r"^(\s*[|»>/•\-]\s*)+$")

_MIN_LEN = 10
_MAX_LEN = 240

# Words that make up navigation/chrome. A line dominated by these is a menu.
_NAV_VOCAB = frozenset({
    "home", "about", "contact", "us", "login", "log", "in", "register", "sign",
    "up", "search", "menu", "downloads", "gallery", "careers", "career", "tenders",
    "tender", "faq", "faqs", "feedback", "newsletter", "subscribe", "follow",
    "share", "print", "sitemap", "english", "nepali", "language", "accessibility",
    "notices", "publications", "reports", "links", "services", "resources",
    "products", "help", "support", "news", "media", "events", "gallery",
})


def _is_nav_menu(s: str) -> bool:
    tokens = [t for t in re.split(r"[\s|»>/•]+", s.lower()) if t]
    if len(tokens) < 3:
        return False
    hits = sum(1 for t in tokens if t.strip(",.:-") in _NAV_VOCAB)
    return hits / len(tokens) >= 0.6


def is_noise(line: str) -> bool:
    s = (line or "").strip()
    if len(s) < _MIN_LEN or len(s) > _MAX_LEN:
        return True
    if _MENU_SEP.match(s):
        return True
    if _NAVWORD.match(s):
        return True
    if _is_nav_menu(s):
        return True
    if _COPYRIGHT.search(s):
        return True
    if _EMAIL.search(s):
        return True
    if _PHONE.search(s):
        return True
    if _ADDRESS.search(s):
        return True
    if _SOCIAL.search(s) and len(s.split()) <= 6:
        return True
    # A line that is mostly a menu of short words separated by pipes/slashes.
    if s.count("|") >= 3 or s.count("»") >= 2:
        return True
    # Require at least a few letters of real text.
    letters = sum(ch.isalpha() for ch in s)
    if letters < 6:
        return True
    return False


def filter_lines(lines: list[str]) -> list[str]:
    """Drop interface noise only. Record-level dedup is owned by records.deduplicate."""
    return [s for ln in lines if not is_noise(s := (ln or "").strip())]

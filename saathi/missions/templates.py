"""Mission templates — the departments a Mission gets, by business type.

A new Mission is never empty: Saathi stands up the departments that business
actually needs. Every template ends with Evidence + Learning — the loop is
universal; only the operating departments differ.
"""
from __future__ import annotations

_COMMON_TAIL = ["Finance", "Automation", "Evidence", "Learning"]

TEMPLATES: dict[str, list[str]] = {
    "travel": ["Executive", "Sales", "Marketing", "Social Media", "Website", "SEO",
               "Customer Support", "CRM"] + _COMMON_TAIL,
    "cafeteria": ["Kitchen", "Inventory", "Purchasing", "Recipes", "Staff", "Waste",
                  "Hygiene"] + _COMMON_TAIL,
    "education": ["Curriculum", "Content Studio", "Publishing", "Community", "Website",
                  "SEO", "Growth"] + _COMMON_TAIL,
    "crypto": ["Research", "Strategy", "Signals", "Portfolio", "Risk", "Subscriptions",
               "Support"] + _COMMON_TAIL,
    "ecommerce": ["Catalog", "Marketing", "Social Media", "Website", "SEO", "Fulfilment",
                  "Customer Support", "CRM"] + _COMMON_TAIL,
    "agency": ["Executive", "Sales", "Delivery", "Marketing", "Content", "SEO", "CRM"] + _COMMON_TAIL,
    "saas": ["Product", "Engineering", "Marketing", "Growth", "Sales", "Support"] + _COMMON_TAIL,
}

# generic fallback for any unclassified business
_GENERIC = ["Executive", "Sales", "Marketing", "Operations", "Customer Support"] + _COMMON_TAIL

# keyword → template, for guessing from a free-text industry string
_INDUSTRY_HINTS = [
    (("travel", "tour", "trip", "holiday", "visa"), "travel"),
    (("cafeteria", "canteen", "restaurant", "food", "kitchen", "cafe"), "cafeteria"),
    (("ielts", "education", "school", "course", "learning", "tutor", "academy"), "education"),
    (("crypto", "trading", "signal", "forex", "invest"), "crypto"),
    (("shop", "store", "ecommerce", "e-commerce", "retail"), "ecommerce"),
    (("agency", "marketing agency", "studio", "consult"), "agency"),
    (("saas", "software", "app", "platform"), "saas"),
]


def guess_type(industry: str, mission_type: str = "") -> str:
    s = (industry or "").lower()
    for keys, tpl in _INDUSTRY_HINTS:
        if any(k in s for k in keys):
            return tpl
    if mission_type in TEMPLATES:
        return mission_type
    return "generic"


def departments_for(*, industry: str = "", mission_type: str = "", template: str = "") -> tuple[str, list[str]]:
    """Return (template_name, departments). Explicit template wins, else guess from industry."""
    tpl = template or guess_type(industry, mission_type)
    return tpl, list(TEMPLATES.get(tpl, _GENERIC))

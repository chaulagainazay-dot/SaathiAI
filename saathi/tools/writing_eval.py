"""
AI Writing Evaluator — Gemini-powered IELTS essay feedback.
Endpoint: POST /api/v1/evaluate/writing
Body: { "essay": str, "task_type": "task1"|"task2", "prompt": str (optional) }
Returns: band_score, criteria, grammar_errors, vocabulary_feedback,
         band8_improvements, band8_rewrite, personal_improvement_plan
"""
import json
import os
import re

from openai import OpenAI

from .. import config


def _heuristic_fallback(essay: str, task_type: str) -> dict:
    words = essay.strip().split()
    word_count = len(words)
    if word_count < 80:    base = 4.0
    elif word_count < 150: base = 5.0
    elif word_count < 200: base = 5.5
    elif word_count < 260: base = 6.0
    else:                  base = 6.5

    linkers = ["however","therefore","moreover","furthermore","although",
               "consequently","nevertheless","in addition","for instance"]
    linker_count = sum(1 for w in words if w.lower().rstrip(".,;:") in linkers)
    if linker_count >= 4:
        base += 0.5
    band = min(base, 7.0)

    criteria_key = "task_response" if task_type == "task2" else "task_achievement"
    return {
        "band_score": band,
        "source": "heuristic",
        "criteria": {
            criteria_key:         {"band": band, "comment": "Heuristic estimate — AI scoring unavailable."},
            "coherence_cohesion": {"band": band, "comment": "Heuristic estimate."},
            "lexical_resource":   {"band": band, "comment": "Heuristic estimate."},
            "grammatical_range":  {"band": band, "comment": "Heuristic estimate."},
        },
        "grammar_errors": [],
        "vocabulary_feedback": {"weak_words": [], "good_phrases": []},
        "band8_improvements": ["Enable AI scoring for detailed feedback."],
        "band8_rewrite": "",
        "personal_improvement_plan": [
            "Complete more practice tests to unlock AI feedback.",
        ],
    }


_SCHEMA_TASK1 = """{
  "band_score": 6.5,
  "criteria": {
    "task_achievement":   {"band": 6.5, "comment": "I noticed your..."},
    "coherence_cohesion": {"band": 7.0, "comment": "I found that..."},
    "lexical_resource":   {"band": 6.0, "comment": "Your vocabulary..."},
    "grammatical_range":  {"band": 6.5, "comment": "I spotted..."}
  },
  "grammar_errors": [
    {"original": "...", "correction": "...", "explanation": "..."}
  ],
  "vocabulary_feedback": {
    "weak_words":   [{"word": "...", "better": "..."}],
    "good_phrases": ["..."]
  },
  "band8_improvements": ["First, ...", "Second, ...", "Third, ..."],
  "band8_rewrite": "Full opening + conclusion rewritten at Band 8",
  "personal_improvement_plan": [
    "Next time, focus on ...",
    "Practice ...",
    "Work on ..."
  ]
}"""

_SCHEMA_TASK2 = _SCHEMA_TASK1.replace('"task_achievement"', '"task_response"')

SYSTEM_PROMPT = """You are Mr. Yeti — a friendly, encouraging IELTS teacher with 15+ years of experience.
You speak in first person, directly to the student ("I noticed...", "I think you should...", "I love that you used...").
Evaluate the {task_label} essay strictly against official IELTS band descriptors (0–9 scale, 0.5 increments).

Return ONLY valid JSON — no markdown fences, no extra text — with this exact structure:
{schema}

Rules:
- band_score = average of the 4 criteria bands, rounded to nearest 0.5
- personal_improvement_plan: exactly 3 actionable items — specific to THIS student's weaknesses
- band8_rewrite: rewrite the full introduction AND conclusion at Band 8 level (minimum 150 words total)
- grammar_errors: up to 5 most important errors only
- All comments must start with "I" (first-person Mr. Yeti voice)

Essay prompt: {prompt}
Essay: {essay}"""


def evaluate_essay(essay: str, task_type: str, prompt: str = "") -> dict:
    if not essay or len(essay.strip()) < 30:
        return _heuristic_fallback(essay or "", task_type)

    api_key = config.GOOGLE_API_KEY
    if not api_key or api_key.startswith("YOUR"):
        return _heuristic_fallback(essay, task_type)

    model = os.getenv("GEMINI_MODEL", config.GEMINI_MODEL)

    if task_type == "task2":
        task_label = "Task 2 (argumentative essay)"
        schema = _SCHEMA_TASK2
    else:
        task_label = "Task 1 (data description / letter)"
        schema = _SCHEMA_TASK1

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        user_msg = SYSTEM_PROMPT.format(
            task_label=task_label,
            schema=schema,
            prompt=prompt or "(no prompt provided)",
            essay=essay,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_msg}],
            temperature=0.3,
            max_tokens=2500,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)
        result["source"] = "gemini"
        return result
    except Exception as exc:
        fallback = _heuristic_fallback(essay, task_type)
        fallback["ai_error"] = str(exc)
        return fallback

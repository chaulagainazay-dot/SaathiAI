"""Deterministic synthetic IELTS content fixtures for local certification.

All content is original fixture material — not live exam material, not copyrighted
official papers. Labeled demo/certification.
"""
from __future__ import annotations

from typing import Any

RUBRIC_VERSION = "ielts.rubric.local.v1"
SCORING_VERSION = "ielts.scoring.local_heuristic.v2"
CONTENT_LABEL = "demo/certification fixture — not official IELTS material"


def speaking_prompts() -> list[dict[str, Any]]:
    return [
        {
            "prompt_id": "sp-p1-hometown",
            "part": "part_1",
            "exam_type": "both",
            "prompt": "Let's talk about your hometown. What do you like most about living there?",
            "prep_seconds": 0,
            "response_seconds": 60,
            "label": CONTENT_LABEL,
        },
        {
            "prompt_id": "sp-p2-journey",
            "part": "part_2",
            "exam_type": "both",
            "prompt": (
                "Describe a journey that was important to you. You should say: "
                "where you went, who you were with, what happened, and why it was important."
            ),
            "prep_seconds": 60,
            "response_seconds": 120,
            "label": CONTENT_LABEL,
        },
        {
            "prompt_id": "sp-p3-travel",
            "part": "part_3",
            "exam_type": "both",
            "prompt": "How has travel changed in your country over the last twenty years?",
            "prep_seconds": 0,
            "response_seconds": 90,
            "label": CONTENT_LABEL,
        },
    ]


def writing_prompts(*, exam_type: str = "academic") -> list[dict[str, Any]]:
    if exam_type == "general_training":
        return [
            {
                "prompt_id": "wr-gt-t1-letter",
                "task": "task_1",
                "exam_type": "general_training",
                "prompt": (
                    "You recently moved to a new neighbourhood. Write a letter to a friend. "
                    "In your letter: describe the neighbourhood, explain why you moved, "
                    "and invite your friend to visit."
                ),
                "min_words": 150,
                "label": CONTENT_LABEL,
            },
            {
                "prompt_id": "wr-gt-t2-essay",
                "task": "task_2",
                "exam_type": "general_training",
                "prompt": (
                    "Some people believe public libraries are no longer necessary because "
                    "of the internet. To what extent do you agree or disagree?"
                ),
                "min_words": 250,
                "label": CONTENT_LABEL,
            },
        ]
    return [
        {
            "prompt_id": "wr-ac-t1-chart",
            "task": "task_1",
            "exam_type": "academic",
            "prompt": (
                "The chart shows the percentage of households with internet access "
                "in three regions from 2010 to 2020. Summarise the information by selecting "
                "and reporting the main features, and make comparisons where relevant."
            ),
            "min_words": 150,
            "label": CONTENT_LABEL,
        },
        {
            "prompt_id": "wr-ac-t2-essay",
            "task": "task_2",
            "exam_type": "academic",
            "prompt": (
                "Universities should focus more on practical skills than theoretical knowledge. "
                "Discuss both views and give your own opinion."
            ),
            "min_words": 250,
            "label": CONTENT_LABEL,
        },
    ]


def reading_fixture(*, exam_type: str = "academic") -> dict[str, Any]:
    """Short original passage with exact-answer key (local only)."""
    if exam_type == "general_training":
        return {
            "passage_id": "rd-gt-notice",
            "exam_type": "general_training",
            "title": "Community Centre Notice (Fixture)",
            "passage": (
                "The Greenfield Community Centre opens Monday to Friday from 8:00 to 18:00. "
                "Weekend classes begin at 9:30. Membership costs NPR 500 per month. "
                "Children under 12 must be accompanied by an adult. "
                "The library room is closed on Tuesdays for cleaning."
            ),
            "questions": [
                {"qid": "q1", "type": "short_answer", "text": "What is the weekday opening time?", "answer": "8:00"},
                {"qid": "q2", "type": "short_answer", "text": "When does the library room close for cleaning?", "answer": "tuesdays"},
                {"qid": "q3", "type": "true_false_not_given", "text": "Membership is free for children under 12.", "answer": "false"},
                {"qid": "q4", "type": "short_answer", "text": "What is the monthly membership fee in NPR?", "answer": "500"},
            ],
            "label": CONTENT_LABEL,
        }
    return {
        "passage_id": "rd-ac-bees",
        "exam_type": "academic",
        "title": "Pollinators and Urban Gardens (Fixture)",
        "passage": (
            "Urban gardens can support pollinator populations when they include continuous "
            "flowering plants. Research in three cities found that small roof gardens "
            "increased local bee visits by roughly 20 percent during summer months. "
            "However, pesticide use reduced diversity of pollinator species. "
            "The study did not measure butterfly populations."
        ),
        "questions": [
            {
                "qid": "q1",
                "type": "true_false_not_given",
                "text": "The study measured butterfly populations.",
                "answer": "false",
            },
            {
                "qid": "q2",
                "type": "short_answer",
                "text": "By approximately what percentage did bee visits increase?",
                "answer": "20",
            },
            {
                "qid": "q3",
                "type": "true_false_not_given",
                "text": "Pesticide use reduced pollinator diversity.",
                "answer": "true",
            },
            {
                "qid": "q4",
                "type": "matching",
                "text": "What supports continuous pollinator populations in cities?",
                "answer": "flowering plants",
            },
        ],
        "label": CONTENT_LABEL,
    }


def listening_fixture() -> dict[str, Any]:
    """Text transcript fixture standing in for audio (labeled)."""
    return {
        "section_id": "ls-s1-library",
        "title": "Library Orientation (Text Fixture)",
        "audio_available": False,
        "modality": "text_transcript_fixture",
        "transcript": (
            "Welcome to the campus library. The silent zone is on the second floor. "
            "Group rooms must be booked online. Late returns cost NPR 10 per day. "
            "The help desk closes at 17:00 on weekdays."
        ),
        "questions": [
            {"qid": "l1", "type": "short_answer", "text": "Which floor is the silent zone on?", "answer": "second"},
            {"qid": "l2", "type": "short_answer", "text": "How much is the late fee per day in NPR?", "answer": "10"},
            {"qid": "l3", "type": "short_answer", "text": "When does the help desk close on weekdays?", "answer": "17:00"},
            {"qid": "l4", "type": "true_false_not_given", "text": "Group rooms can be booked online.", "answer": "true"},
        ],
        "label": CONTENT_LABEL,
    }


# Indicative raw→band mapping tables (NOT official; labeled for practice only)
ACADEMIC_READING_BANDS = {
    0: 0.0, 1: 2.5, 2: 3.5, 3: 4.5, 4: 5.5,
}
GENERAL_READING_BANDS = {
    0: 0.0, 1: 3.0, 2: 4.0, 3: 5.0, 4: 6.0,
}
LISTENING_BANDS = {
    0: 0.0, 1: 3.0, 2: 4.0, 3: 5.0, 4: 6.0,
}


def indicative_band_from_raw(correct: int, total: int, table: dict[int, float]) -> dict[str, Any]:
    correct = max(0, min(int(correct), int(total)))
    band = table.get(correct, table.get(max(table), 0.0))
    return {
        "raw_correct": correct,
        "raw_total": total,
        "indicative_band": band,
        "official": False,
        "conversion_label": "indicative only — not an official IELTS conversion",
        "rubric_version": RUBRIC_VERSION,
        "scoring_version": SCORING_VERSION,
    }

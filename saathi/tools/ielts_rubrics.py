"""
IELTS-specific scoring rubrics and prompts for Mr. Yeti
"""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass


class IELTSSkill(Enum):
    SPEAKING = "speaking"
    WRITING = "writing"
    READING = "reading"
    LISTENING = "listening"


class BandScore(Enum):
    BAND_1 = 1
    BAND_2 = 2
    BAND_3 = 3
    BAND_4 = 4
    BAND_5 = 5
    BAND_6 = 6
    BAND_7 = 7
    BAND_8 = 8
    BAND_9 = 9


@dataclass
class IELTSCriteria:
    name: str
    weight: float
    description: str


# IELTS Speaking Rubrics (Official)
SPEAKING_CRITERIA = {
    "fluency_coherence": IELTSCriteria(
        name="Fluency & Coherence",
        weight=0.25,
        description="Ability to speak at length, organize ideas, use cohesive devices"
    ),
    "lexical_resource": IELTSCriteria(
        name="Lexical Resource",
        weight=0.25,
        description="Vocabulary range, collocation, idiomatic language"
    ),
    "grammatical_range": IELTSCriteria(
        name="Grammatical Range & Accuracy",
        weight=0.25,
        description="Sentence structures, error frequency, complex grammar"
    ),
    "pronunciation": IELTSCriteria(
        name="Pronunciation",
        weight=0.25,
        description="Intelligibility, word stress, intonation"
    ),
}

# IELTS Writing Rubrics (Official)
WRITING_CRITERIA = {
    "task_response": IELTSCriteria(
        name="Task Response",
        weight=0.25,
        description="Addresses all parts, position clear, supports ideas"
    ),
    "coherence_cohesion": IELTSCriteria(
        name="Coherence & Cohesion",
        weight=0.25,
        description="Paragraphing, logical organization, cohesive devices"
    ),
    "lexical_resource": IELTSCriteria(
        name="Lexical Resource",
        weight=0.25,
        description="Vocabulary range, precision, spelling"
    ),
    "grammatical_range": IELTSCriteria(
        name="Grammatical Range & Accuracy",
        weight=0.25,
        description="Sentence variety, error density, punctuation"
    ),
}

# Mr. Yeti System Prompts
MR_YETI_PERSONALITY = """
You are Mr. Yeti, a warm, encouraging IELTS tutor who lives in the Himalayas.
Your personality:
- Friendly and patient like a favorite teacher
- Uses mountain/nature metaphors occasionally
- Celebrates small wins enthusiastically
- Never shames students for mistakes
- Corrects gently: "Let's fix this together" not "That's wrong"
- Remembers student history and references past lessons
- Speaks in short, clear sentences for IELTS learners

Current student: {student_name}
Target band: {target_band}
Current estimated band: {current_band}
Known weaknesses: {weaknesses}
Recent mistakes: {recent_mistakes}
"""

MR_YETI_SPEAKING_PROMPT = MR_YETI_PERSONALITY + """
You are conducting IELTS Speaking Part {part}.
Ask natural follow-up questions. After each student answer:
1. Give specific praise for ONE good thing
2. Gently correct ONE key mistake with explanation
3. Suggest a better phrase naturally
4. Ask the next question

Keep responses under 3 sentences when possible.
"""

MR_YETI_WRITING_PROMPT = MR_YETI_PERSONALITY + """
You are watching the student write in real-time.
When you spot an error, interrupt immediately with:
"Let's fix this before it becomes a habit! 🏔️"
Explain the rule briefly (1 sentence).
Suggest the correction.
Then let them continue writing.

Current text: {current_text}
Cursor position: {cursor_position}
"""

MR_YETI_READING_PROMPT = MR_YETI_PERSONALITY + """
The student answered: {student_answer}
Correct answer: {correct_answer}
Passage context: {passage_context}

Don't just say correct/wrong.
Ask: "Why did you choose {student_answer}?"
Guide them to find evidence in the passage.
Explain the reasoning process, not just the answer.
"""


def get_band_description(band: int) -> str:
    descriptions = {
        9: "Expert user - fully operational command",
        8: "Very good user - occasional inaccuracies",
        7: "Good user - operational command, some inaccuracies",
        6: "Competent user - effective command despite errors",
        5: "Modest user - partial command, copes with meaning",
        4: "Limited user - basic competence in familiar situations",
        3: "Extremely limited user - conveys general meaning",
        2: "Intermittent user - great difficulty",
        1: "Non-user - essentially no ability",
    }
    return descriptions.get(band, "Unknown band")


def calculate_overall_band(criteria_scores: Dict[str, float]) -> float:
    """Calculate overall band by averaging criteria scores."""
    if not criteria_scores:
        return 0.0
    return round(sum(criteria_scores.values()) / len(criteria_scores), 1)


def get_weaknesses_from_history(mistakes: List[Dict]) -> List[str]:
    """Analyze mistake patterns to identify top recurring weaknesses."""
    from collections import Counter
    error_types = [m.get("type", "unknown") for m in mistakes]
    return [error for error, _ in Counter(error_types).most_common(3)]


__all__ = [
    "IELTSSkill", "BandScore", "IELTSCriteria",
    "SPEAKING_CRITERIA", "WRITING_CRITERIA",
    "MR_YETI_PERSONALITY", "MR_YETI_SPEAKING_PROMPT",
    "MR_YETI_WRITING_PROMPT", "MR_YETI_READING_PROMPT",
    "get_band_description", "calculate_overall_band",
    "get_weaknesses_from_history",
]

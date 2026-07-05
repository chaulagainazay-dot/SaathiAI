"""365-Day Mr. Yeti IELTS Curriculum — decide WHAT to teach once, so the factory
can focus on HOW to teach it best.

Fixed syllabus by phase (Ajay's structure):
  Days   1– 90  Grammar fundamentals
  Days  91–180  Vocabulary
  Days 181–240  Speaking
  Days 241–300  Writing Task 1
  Days 301–365  Writing Task 2 + Listening + Reading strategies

`lesson_for_day(day)` and `today()` are deterministic — no state, no daily
"what should I teach?" decision. Analytics later adapt presentation (hook, length,
examples), never the syllabus. One lesson feeds every business: video, PIELTS
lesson, Telegram quiz, blog, social. See docs/PAT-CHECKLIST.md.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

# ── topic banks (real IELTS content; wrapped to fill each phase) ──────────────
_GRAMMAR = [
    "Present Simple vs Present Continuous", "Past Simple vs Present Perfect",
    "Present Perfect vs Present Perfect Continuous", "Past Perfect Tense",
    "Past Continuous for interrupted actions", "Future with will vs going to",
    "Future Continuous and Future Perfect", "The Passive Voice",
    "First Conditional", "Second Conditional", "Third Conditional", "Mixed Conditionals",
    "Modal verbs of possibility", "Modal verbs of obligation", "Modals of deduction",
    "Reported Speech: statements", "Reported Speech: questions", "Relative Clauses (defining)",
    "Relative Clauses (non-defining)", "Articles: a, an, the", "Countable vs uncountable nouns",
    "Quantifiers: much, many, few, little", "Comparatives and Superlatives",
    "Gerunds vs Infinitives", "Verb patterns", "Phrasal verbs basics",
    "Prepositions of time", "Prepositions of place", "Linking words for contrast",
    "Linking words for cause and effect", "Subject-verb agreement", "Question formation",
    "Tag questions", "Used to vs would for past habits", "Wish and if only",
    "Causative have and get", "Inversion for emphasis", "Cleft sentences",
    "Participle clauses", "Determiners", "The subjunctive", "Adverbs of frequency",
    "Word order in sentences", "Punctuation for clarity", "Common grammar mistakes",
]
_VOCAB = [
    "Describing trends (graphs)", "Education vocabulary", "Environment and climate",
    "Technology and the internet", "Health and lifestyle", "Work and careers",
    "Travel and tourism", "Crime and justice", "Money and economy", "Family and relationships",
    "Media and advertising", "Art and culture", "Science and research", "Food and diet",
    "Housing and cities", "Transport and traffic", "Globalisation", "Government and society",
    "Collocations for Band 7+", "Academic verbs", "Formal vs informal words",
    "Idioms for speaking", "Phrasal verbs for daily life", "Synonyms to avoid repetition",
    "Adjectives to describe people", "Words for opinions", "Words for agreeing/disagreeing",
    "Linking phrases for essays", "Vocabulary for cause and effect", "Vocabulary for solutions",
]
_SPEAKING = [
    "Part 1: Talking about yourself", "Part 1: Your hometown", "Part 1: Work or study",
    "Part 1: Hobbies", "Part 2: Describe a person you admire", "Part 2: Describe a place",
    "Part 2: Describe an object", "Part 2: Describe an event", "Part 2: Describe an experience",
    "Part 3: Abstract discussion", "Fluency and coherence", "Avoiding hesitation",
    "Paraphrasing under pressure", "Pronunciation: word stress", "Pronunciation: intonation",
    "Connected speech", "Extending your answers", "Giving reasons and examples",
    "Expressing opinions politely", "Speculating about the future", "Comparing past and present",
    "Handling difficult questions", "Signposting your ideas", "Natural fillers vs bad habits",
    "Describing feelings precisely", "Storytelling in Part 2", "Using a range of tenses",
    "Sounding confident", "Common Part 3 themes", "Mock speaking test walkthrough",
]
_TASK1 = [
    "Line graphs: describing change over time", "Bar charts: comparing groups",
    "Pie charts: proportions", "Tables: selecting key data", "Maps: describing changes",
    "Process diagrams", "Mixed charts", "Writing an overview", "Grouping data logically",
    "Language of increase and decrease", "Describing stability and fluctuation",
    "Making comparisons", "Approximation language", "Structuring Task 1 in 4 paragraphs",
    "Avoiding common Task 1 mistakes", "Paraphrasing the question", "Selecting main features",
    "Time management for Task 1", "Cohesion in Task 1", "Task 1 band 8 model analysis",
]
_TASK2_ETC = [
    "Task 2: Opinion (agree/disagree) essays", "Task 2: Discussion (both views) essays",
    "Task 2: Problem and solution essays", "Task 2: Advantages and disadvantages",
    "Task 2: Two-part questions", "Writing a clear thesis", "Topic sentences",
    "Developing ideas with examples", "Counter-arguments", "Conclusions that add value",
    "Cohesion and coherence", "Formal academic tone", "Common Task 2 mistakes",
    "Planning an essay in 5 minutes", "Task 2 band 8 model analysis",
    "Listening: multiple choice", "Listening: form completion", "Listening: matching",
    "Listening: map labelling", "Listening: predicting answers", "Listening: keeping up with speed",
    "Reading: skimming and scanning", "Reading: True/False/Not Given",
    "Reading: matching headings", "Reading: sentence completion", "Reading: managing time",
    "Reading: dealing with unknown words", "Reading: paragraph matching",
    "Exam-day strategy overview", "Full mock test review", "Band 9 study routine",
]

# (phase name, skill tag, day_start, day_end, topic bank)
PHASES = [
    ("Grammar Fundamentals", "grammar", 1, 90, _GRAMMAR),
    ("Vocabulary Building", "vocabulary", 91, 180, _VOCAB),
    ("Speaking Mastery", "speaking", 181, 240, _SPEAKING),
    ("Writing Task 1", "writing-task1", 241, 300, _TASK1),
    ("Writing Task 2 + Listening + Reading", "exam-strategy", 301, 365, _TASK2_ETC),
]


@dataclass
class Lesson:
    day: int
    phase: str
    skill: str
    topic: str

    def as_dict(self) -> dict:
        return {"day": self.day, "phase": self.phase, "skill": self.skill, "topic": self.topic}


def lesson_for_day(day: int) -> Lesson:
    """Deterministic: day 1..365 → a lesson. Days outside range wrap into the year."""
    day = ((int(day) - 1) % 365) + 1
    for name, skill, start, end, bank in PHASES:
        if start <= day <= end:
            topic = bank[(day - start) % len(bank)]
            return Lesson(day=day, phase=name, skill=skill, topic=topic)
    # unreachable (phases cover 1..365), but stay safe
    return Lesson(day=day, phase=PHASES[0][0], skill=PHASES[0][1], topic=_GRAMMAR[0])


def today(now: float | None = None) -> Lesson:
    """Today's lesson. Anchored to SAATHI_CURRICULUM_START (YYYY-MM-DD) if set —
    day N = days since start + 1 — else falls back to day-of-year."""
    now = now or time.time()
    start = os.getenv("SAATHI_CURRICULUM_START")
    if start:
        try:
            import datetime as dt
            s = dt.date.fromisoformat(start)
            return lesson_for_day((dt.date.fromtimestamp(now) - s).days + 1)
        except Exception:
            pass
    return lesson_for_day(int(time.strftime("%j", time.localtime(now))))

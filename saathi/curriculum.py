"""IELTS Mastery — a versioned learning program (not just a 365-day list).

Two ideas the CTO called out:

1. **Versioned program with a start date.** Every learner — including Ajay —
   begins at Day 1 relative to THEIR enrolment, never dropped into Day 287. The
   channel publishes in program order from the program start date.

2. **Curriculum day ≠ episode number.** Curriculum day is per-learner progress;
   the episode number is the global publishing counter (Day 41 → EP-041 →
   "Mr. Yeti #41"). Keep them separate.

`lesson_for_day(day)` returns a rich `Lesson` object every department consumes
(video, PIELTS lesson, flashcards, quiz, blog, social). Deep pedagogical fields
(grammar_points, quiz, tasks…) start empty and are filled by the content pipeline
on demand — the curriculum owns the SPEC, not fabricated lesson content.

v0.4.1 keeps the exam-section ordering (grammar→vocab→speaking→writing→strategy).
The spiral model (a little of every skill each day) is a deliberate v0.5 change,
to be driven by real learning analytics — not assumed now.
"""
from __future__ import annotations

import datetime as _dt
import os
import time
from dataclasses import dataclass, field

# ── the program ───────────────────────────────────────────────────────────────
PROGRAM_NAME = "IELTS Mastery"
PROGRAM_VERSION = "v1"
PROGRAM_START = "2026-07-06"          # channel publishing start; override via env


@dataclass
class Program:
    name: str
    version: str
    start_date: str

    @property
    def title(self) -> str:
        return f"{self.name} {self.version}"


def program(now: float | None = None) -> Program:
    return Program(PROGRAM_NAME, PROGRAM_VERSION,
                   os.getenv("SAATHI_CURRICULUM_START", PROGRAM_START))


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

# (phase name, skill tag, day_start, day_end, topic bank, CEFR difficulty)
PHASES = [
    ("Grammar Fundamentals", "grammar", 1, 90, _GRAMMAR, "B1"),
    ("Vocabulary Building", "vocabulary", 91, 180, _VOCAB, "B2"),
    ("Speaking Mastery", "speaking", 181, 240, _SPEAKING, "B2"),
    ("Writing Task 1", "writing-task1", 241, 300, _TASK1, "B2"),
    ("Writing Task 2 + Listening + Reading", "exam-strategy", 301, 365, _TASK2_ETC, "C1"),
]


@dataclass
class Lesson:
    day: int
    phase: str
    skill: str
    topic: str
    objective: str
    difficulty: str
    estimated_minutes: int
    prerequisites: list[int]
    seo_keywords: list[str]
    youtube_title: str
    # enrichable by the content pipeline (Research/Script directors); spec only here
    grammar_points: list = field(default_factory=list)
    vocabulary: list = field(default_factory=list)
    common_mistakes: list = field(default_factory=list)
    speaking_task: list = field(default_factory=list)
    writing_task: list = field(default_factory=list)
    reading_task: list = field(default_factory=list)
    listening_task: list = field(default_factory=list)
    quiz: list = field(default_factory=list)
    homework: list = field(default_factory=list)

    @property
    def episode(self) -> str:
        return f"EP-{self.day:03d}"

    @property
    def youtube_number(self) -> str:
        return f"Mr. Yeti #{self.day}"

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["episode"] = self.episode
        d["youtube_number"] = self.youtube_number
        return d


def lesson_for_day(day: int) -> Lesson:
    """Deterministic: day 1..365 → a rich Lesson. Days outside range wrap into the year."""
    day = ((int(day) - 1) % 365) + 1
    for name, skill, start, end, bank, diff in PHASES:
        if start <= day <= end:
            topic = bank[(day - start) % len(bank)]
            # grammar deepens B1→B2 across its 90 days
            difficulty = "B2" if (skill == "grammar" and day > 45) else diff
            prereqs = [d for d in (day - 2, day - 1) if start <= d < day]
            return Lesson(
                day=day, phase=name, skill=skill, topic=topic,
                objective=f"Understand and correctly use {topic.lower()} for IELTS {skill}.",
                difficulty=difficulty, estimated_minutes=18, prerequisites=prereqs,
                seo_keywords=[topic, "IELTS", skill, "Mr Yeti", f"IELTS {skill}"],
                youtube_title=f"Mr. Yeti #{day}: {topic} | IELTS {name}")
    return lesson_for_day(1)  # unreachable (phases cover 1..365)


# ── program-day vs learner-day ────────────────────────────────────────────────
def _start_date(now: float) -> _dt.date:
    raw = os.getenv("SAATHI_CURRICULUM_START", PROGRAM_START)
    try:
        return _dt.date.fromisoformat(raw)
    except Exception:
        return _dt.date.fromtimestamp(now)


def program_day(now: float | None = None) -> int:
    """Days since the program start (channel/publishing counter). Clamped to ≥1
    so a pre-launch preview shows Day 1 rather than 0/negative."""
    now = now or time.time()
    day = (_dt.date.fromtimestamp(now) - _start_date(now)).days + 1
    return max(1, day)


def learner_day(enrolled: str | _dt.date, now: float | None = None) -> int:
    """Per-learner progress: Day 1 on the day they enrolled, never dropped mid-program."""
    now = now or time.time()
    e = _dt.date.fromisoformat(enrolled) if isinstance(enrolled, str) else enrolled
    return max(1, (_dt.date.fromtimestamp(now) - e).days + 1)


def today(now: float | None = None) -> Lesson:
    """Today's lesson on the program schedule (episode = program_day)."""
    return lesson_for_day(program_day(now))

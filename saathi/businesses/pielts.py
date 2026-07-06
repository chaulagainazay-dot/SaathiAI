"""PIELTS business event source — converts PIELTS's native events into Evidence.

PIELTS (the IELTS app + Ajay's own study) emits meaningful actions as events:
lesson.completed, essay.scored, mistake.detected, quiz.completed, word.learned,
streak.updated, subscription.started, user.feedback. This module is the ONLY
place that understands PIELTS semantics; PIELTS itself just POSTs events and knows
nothing about Evidence. The strongest flywheel: essay.scored → a common mistake →
tomorrow's Mr. Yeti video → Telegram quiz → back into PIELTS.
"""
from __future__ import annotations

from saathi.evidence.schema import Evidence

_P = "pielts"


def _band(payload) -> float | None:
    b = payload.get("band")
    return float(b) if isinstance(b, (int, float)) else None


def handle(event_type: str, payload: dict, *, subject: str = "") -> list[Evidence]:
    """One PIELTS event → Evidence rows. Returns [] for signals we only want raw."""
    p = payload or {}
    subject = subject or p.get("id") or p.get("essay_id") or p.get("lesson_id") or ""
    user = p.get("user_id") or p.get("student", "")

    if event_type == "essay.scored":
        return [Evidence(
            department=_P, project=_P, episode=subject, director="writing_evaluator",
            prompt_version=p.get("prompt_version", ""), provider="gemini", model=p.get("model", ""),
            confidence=float(p.get("confidence", 0) or 0), status="graded",
            metrics={"band": _band(p), "topic": p.get("topic", ""), "task": p.get("task", ""),
                     "corrections": p.get("corrections", 0), "user": user},
            feedback={"student_rating": p.get("student_rating")})]

    if event_type == "mistake.detected":
        return [Evidence(
            department=_P, project=_P, episode=subject, director="writing_evaluator",
            status="mistake", confidence=float(p.get("confidence", 0) or 0),
            metrics={"topic": p.get("topic", ""), "mistake": p.get("mistake", ""),
                     "skill": p.get("skill", ""), "user": user})]

    if event_type in ("lesson.completed", "revision.completed"):
        return [Evidence(
            department=_P, project=_P, episode=subject, director="curriculum",
            status="completed",
            metrics={"topic": p.get("topic", ""), "skill": p.get("skill", ""),
                     "seconds": p.get("seconds", 0), "score": p.get("score"), "user": user})]

    if event_type == "quiz.completed":
        total = p.get("total") or 0
        correct = p.get("correct") or 0
        acc = round(correct / total, 3) if total else None
        return [Evidence(
            department=_P, project=_P, episode=subject, director="curriculum", status="quiz",
            confidence=acc or 0.0,
            metrics={"topic": p.get("topic", ""), "accuracy": acc, "correct": correct,
                     "total": total, "user": user})]

    if event_type == "user.feedback":
        return [Evidence(
            department=_P, project=_P, episode=subject, director="curriculum", status="feedback",
            metrics={"user": user}, feedback={"rating": p.get("rating"), "text": p.get("text", "")})]

    if event_type == "subscription.started":
        return [Evidence(
            department=_P, project=_P, episode=subject, director="revenue", status="subscribed",
            metrics={"plan": p.get("plan", ""), "amount": p.get("amount"), "user": user})]

    # word.learned / streak.updated / *.started → keep as raw event signal, no evidence yet
    return []

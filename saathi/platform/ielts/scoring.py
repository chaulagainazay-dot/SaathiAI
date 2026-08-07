"""Provider-neutral IELTS practice feedback with a deterministic local fallback."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from saathi.platform.ielts.content import (
    ACADEMIC_READING_BANDS,
    GENERAL_READING_BANDS,
    LISTENING_BANDS,
    RUBRIC_VERSION,
    SCORING_VERSION,
    indicative_band_from_raw,
)


LIMITATION = (
    "Local heuristic result for practice only. It is not an official IELTS score "
    "and does not replace assessment by a qualified examiner."
)

PRONUNCIATION_TEXT_ONLY = (
    "Pronunciation is not inferred from text-only input. Acoustic analysis was not performed."
)


class ScoringProvider(Protocol):
    def health(self) -> dict: ...
    def capabilities(self) -> dict: ...
    def score_writing(self, *, prompt: str, response: str, task_type: str) -> dict: ...
    def score_speaking(self, *, prompt: str, transcript: str, part: str, has_audio: bool) -> dict: ...


class ScoringProviderUnavailable(RuntimeError):
    """Safe provider-boundary error; never includes upstream details."""


@dataclass(frozen=True)
class UnavailableScoringProvider:
    """Explicit no-provider adapter used when no governed integration is configured."""

    provider_id: str = "provider_not_configured"

    def health(self) -> dict:
        return {
            "status": "unavailable",
            "provider": self.provider_id,
            "reason": "not_configured",
            "network_required": False,
        }

    def capabilities(self) -> dict:
        return {
            "writing": False,
            "speaking_transcript": False,
            "audio_analysis": False,
            "official_scoring": False,
        }

    def score_writing(self, **_kwargs) -> dict:
        raise ScoringProviderUnavailable("provider-assisted scoring is unavailable")

    def score_speaking(self, **_kwargs) -> dict:
        raise ScoringProviderUnavailable("provider-assisted scoring is unavailable")


@dataclass(frozen=True)
class LocalHeuristicScorer:
    provider_id: str = "local_heuristic_v1"

    def health(self) -> dict:
        return {"status": "available", "provider": self.provider_id, "network_required": False}

    def capabilities(self) -> dict:
        return {"writing": True, "speaking_transcript": True, "audio_analysis": False, "official_scoring": False}

    @staticmethod
    def _signals(text: str) -> dict:
        words = re.findall(r"[A-Za-z']+", text.lower())
        sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
        unique = len(set(words))
        linkers = sum(words.count(x) for x in ("however", "therefore", "although", "moreover", "because", "while"))
        return {
            "word_count": len(words),
            "sentence_count": len(sentences),
            "lexical_variety": round(unique / max(1, len(words)), 2),
            "linking_markers": linkers,
        }

    @staticmethod
    def _level(signals: dict) -> str:
        words = signals["word_count"]
        if words < 60:
            return "developing"
        if words < 140:
            return "functional"
        return "established"

    @staticmethod
    def _level_to_band(level: str) -> float:
        return {"developing": 5.0, "functional": 6.0, "established": 7.0}.get(level, 5.5)

    def score_writing(self, *, prompt: str, response: str, task_type: str) -> dict:
        signals = self._signals(response)
        level = self._level(signals)
        band = self._level_to_band(level)
        task_key = "task_achievement" if "task_1" in (task_type or "") else "task_response"
        return {
            "label": "practice estimate",
            "source": self.provider_id,
            "official": False,
            "overall_level": level,
            "estimated_overall_band": band,
            "confidence": 0.45,
            "confidence_label": "low–moderate; heuristic only",
            "rubric_version": RUBRIC_VERSION,
            "scoring_version": SCORING_VERSION,
            "criteria": {
                task_key: {
                    "level": level,
                    "estimated_band": band,
                    "feedback": "Check that each main claim directly answers the prompt.",
                },
                "coherence_and_cohesion": {
                    "level": level,
                    "estimated_band": band,
                    "feedback": f"{signals['linking_markers']} explicit linking markers detected.",
                },
                "lexical_resource": {
                    "level": level,
                    "estimated_band": band,
                    "feedback": f"Lexical variety signal: {signals['lexical_variety']:.2f}.",
                },
                "grammatical_range_and_accuracy": {
                    "level": level,
                    "estimated_band": band,
                    "feedback": f"{signals['sentence_count']} sentence boundaries detected; manual accuracy review is still required.",
                },
            },
            "priority_improvement": "Strengthen task response with one clear controlling idea per paragraph.",
            "signals": signals,
            "limitations": [LIMITATION, "The local estimator does not verify factual accuracy or nuanced grammar."],
        }

    def score_speaking(self, *, prompt: str, transcript: str, part: str, has_audio: bool) -> dict:
        signals = self._signals(transcript)
        level = self._level(signals)
        band = self._level_to_band(level)
        pronunciation = {
            "level": "not_assessed" if not has_audio else "indicative_only",
            "estimated_band": None if not has_audio else band,
            "feedback": PRONUNCIATION_TEXT_ONLY if not has_audio else "Limited local signal only; not acoustic certification.",
        }
        return {
            "label": "indicative feedback",
            "source": self.provider_id,
            "official": False,
            "overall_level": level,
            "estimated_overall_band": band if transcript.strip() else None,
            "confidence": 0.35 if not has_audio else 0.4,
            "confidence_label": "low; text-only input" if not has_audio else "low–moderate",
            "input_modality": "audio_plus_transcript" if has_audio else "text_transcript_only",
            "rubric_version": RUBRIC_VERSION,
            "scoring_version": SCORING_VERSION,
            "criteria": {
                "fluency_and_coherence": {
                    "level": level,
                    "estimated_band": band,
                    "feedback": "Transcript structure only; pauses and delivery are not measured.",
                },
                "lexical_resource": {
                    "level": level,
                    "estimated_band": band,
                    "feedback": f"Lexical variety signal: {signals['lexical_variety']:.2f}.",
                },
                "grammatical_range_and_accuracy": {
                    "level": level,
                    "estimated_band": band,
                    "feedback": "Manual review is required for spoken-form accuracy.",
                },
                "pronunciation": pronunciation,
            },
            "priority_improvement": "Expand answers with one reason and one example per question.",
            "signals": signals,
            "audio_analysis_performed": False,
            "acoustic_pronunciation_claimed": False,
            "limitations": [LIMITATION, PRONUNCIATION_TEXT_ONLY],
        }

    def score_objective(
        self,
        *,
        skill: str,
        exam_type: str,
        answers: list[str],
        key: list[dict[str, Any]],
    ) -> dict:
        """Exact-match scoring for reading/listening fixtures."""
        normalized = [re.sub(r"\s+", " ", (a or "").strip().lower()) for a in answers]
        correct = 0
        detail = []
        for i, q in enumerate(key):
            expected = re.sub(r"\s+", " ", str(q.get("answer") or "").strip().lower())
            got = normalized[i] if i < len(normalized) else ""
            ok = bool(got) and (got == expected or expected in got or got in expected)
            if ok:
                correct += 1
            detail.append({
                "qid": q.get("qid"),
                "correct": ok,
                "unanswered": not got,
                "expected_label": "hidden_from_public_response",
            })
        total = len(key)
        if skill == "listening":
            table = LISTENING_BANDS
        elif exam_type == "general_training":
            table = GENERAL_READING_BANDS
        else:
            table = ACADEMIC_READING_BANDS
        band_info = indicative_band_from_raw(correct, total, table)
        unanswered = sum(1 for d in detail if d["unanswered"])
        return {
            "label": "deterministic objective practice result",
            "source": self.provider_id,
            "official": False,
            "skill": skill,
            "exam_type": exam_type,
            "answers_recorded": len([a for a in normalized if a]),
            "correct": correct,
            "total": total,
            "unanswered": unanswered,
            "items": detail,
            "estimated_overall_band": band_info["indicative_band"],
            "band_conversion": band_info,
            "confidence": 0.7 if unanswered == 0 else 0.5,
            "confidence_label": "moderate for fixture key; conversion is indicative only",
            "rubric_version": RUBRIC_VERSION,
            "scoring_version": SCORING_VERSION,
            "limitations": [
                LIMITATION,
                band_info["conversion_label"],
                "Fixture answer key only — not an official test form.",
            ],
        }


@dataclass(frozen=True)
class SafeFallbackScorer:
    """Use a provider when safe, otherwise return explicitly labelled local output."""

    primary: ScoringProvider
    fallback: LocalHeuristicScorer = LocalHeuristicScorer()

    def health(self) -> dict:
        try:
            primary_status = str(self.primary.health().get("status", "unavailable"))
        except Exception:
            primary_status = "unavailable"
        return {
            "status": "available_with_local_fallback",
            "provider_assisted": primary_status,
            "fallback": self.fallback.health(),
            "official_scoring": False,
        }

    def capabilities(self) -> dict:
        return {
            **self.fallback.capabilities(),
            "provider_assisted": self.health()["provider_assisted"] == "available",
        }

    @staticmethod
    def _safe_local(result: dict) -> dict:
        return {
            **result,
            "official": False,
            "provider_assisted": False,
            "fallback": {"used": True, "reason": "provider_unavailable"},
        }

    def score_writing(self, *, prompt: str, response: str, task_type: str) -> dict:
        try:
            result = dict(self.primary.score_writing(
                prompt=prompt, response=response, task_type=task_type
            ))
            return {
                **result,
                "label": "provider-assisted estimate",
                "official": False,
                "provider_assisted": True,
            }
        except Exception:
            return self._safe_local(self.fallback.score_writing(
                prompt=prompt, response=response, task_type=task_type
            ))

    def score_speaking(
        self, *, prompt: str, transcript: str, part: str, has_audio: bool
    ) -> dict:
        try:
            result = dict(self.primary.score_speaking(
                prompt=prompt, transcript=transcript, part=part, has_audio=has_audio
            ))
            return {
                **result,
                "label": "provider-assisted estimate",
                "official": False,
                "provider_assisted": True,
                "acoustic_pronunciation_claimed": False,
            }
        except Exception:
            return self._safe_local(self.fallback.score_speaking(
                prompt=prompt, transcript=transcript, part=part, has_audio=has_audio
            ))

    def score_objective(
        self,
        *,
        skill: str,
        exam_type: str,
        answers: list[str],
        key: list[dict[str, Any]],
    ) -> dict:
        # Objective fixture scoring is always local deterministic
        return {
            **self.fallback.score_objective(
                skill=skill, exam_type=exam_type, answers=answers, key=key
            ),
            "provider_assisted": False,
            "official": False,
        }

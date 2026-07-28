"""Provider-neutral IELTS practice feedback with a deterministic local fallback."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


LIMITATION = (
    "Local heuristic result for practice only. It is not an official IELTS score "
    "and does not replace assessment by a qualified examiner."
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

    def score_writing(self, *, prompt: str, response: str, task_type: str) -> dict:
        signals = self._signals(response)
        level = self._level(signals)
        return {
            "label": "practice estimate",
            "source": self.provider_id,
            "official": False,
            "overall_level": level,
            "criteria": {
                "task_response": {"level": level, "feedback": "Check that each main claim directly answers the prompt."},
                "coherence_and_cohesion": {"level": level, "feedback": f"{signals['linking_markers']} explicit linking markers detected."},
                "lexical_resource": {"level": level, "feedback": f"Lexical variety signal: {signals['lexical_variety']:.2f}."},
                "grammatical_range_and_accuracy": {"level": level, "feedback": f"{signals['sentence_count']} sentence boundaries detected; manual accuracy review is still required."},
            },
            "signals": signals,
            "limitations": [LIMITATION, "The local estimator does not verify factual accuracy or nuanced grammar."],
        }

    def score_speaking(self, *, prompt: str, transcript: str, part: str, has_audio: bool) -> dict:
        signals = self._signals(transcript)
        level = self._level(signals)
        return {
            "label": "indicative feedback",
            "source": self.provider_id,
            "official": False,
            "overall_level": level,
            "criteria": {
                "fluency_and_coherence": {"level": level, "feedback": "Transcript structure only; pauses and delivery are not measured."},
                "lexical_resource": {"level": level, "feedback": f"Lexical variety signal: {signals['lexical_variety']:.2f}."},
                "grammatical_range_and_accuracy": {"level": level, "feedback": "Manual review is required for spoken-form accuracy."},
                "pronunciation": {"level": "not_assessed", "feedback": "Pronunciation is not inferred from a transcript."},
            },
            "signals": signals,
            "audio_analysis_performed": False,
            "limitations": [LIMITATION, "Pronunciation and acoustic fluency were not assessed."],
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
            }
        except Exception:
            return self._safe_local(self.fallback.score_speaking(
                prompt=prompt, transcript=transcript, part=part, has_audio=has_audio
            ))

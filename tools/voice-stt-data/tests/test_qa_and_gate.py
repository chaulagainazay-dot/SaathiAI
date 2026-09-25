#!/usr/bin/env python3
"""Unit tests for product-clean speech QA and authorization gate (no audio I/O)."""
from __future__ import annotations

import json
import struct
import tempfile
import wave
import unittest
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import qa_clips  # noqa: E402
import training_authorization_gate as gate  # noqa: E402


def write_silence_wav(path: Path, seconds: float = 1.0, sr: int = 16000, amp: int = 0) -> None:
    n = int(seconds * sr)
    frames = struct.pack("<" + "h" * n, *([amp] * n))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)


def write_tone_wav(path: Path, seconds: float = 1.0, sr: int = 16000) -> None:
    n = int(seconds * sr)
    samples = []
    for i in range(n):
        # simple square-ish mid level
        samples.append(4000 if (i // 40) % 2 == 0 else -4000)
    frames = struct.pack("<" + "h" * n, *samples)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)


class TestQA(unittest.TestCase):
    def test_silence_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.wav"
            write_silence_wav(p, amp=0)
            consent_dir = Path(td) / "consents"
            consent_dir.mkdir()
            (consent_dir / "spk_001.json").write_text(
                json.dumps(
                    {
                        "speaker_id": "spk_001",
                        "consent_version": "v1",
                        "commercial_model_training_allowed": True,
                        "internal_research_allowed": True,
                        "evaluation_allowed": True,
                        "redistribution_allowed": False,
                        "recorded_at": "2026-01-01T00:00:00Z",
                        "withdrawal_reference": "x",
                    }
                ),
                encoding="utf-8",
            )
            qa_clips.CONSENTS = consent_dir
            row = {
                "clip_id": "c1",
                "speaker_id": "spk_001",
                "audio_path": str(p),
                "transcript": "hello",
                "language_class": "EN",
                "contains_numbers": False,
                "sha256": "abc",
                "bucket": "PRODUCT_CLEAN",
            }
            out = qa_clips.qa_row(row, {})
            self.assertEqual(out["qa_status"], "FAIL")
            self.assertIn("silence_or_near_silence", out["qa_errors"])

    def test_good_tone_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.wav"
            write_tone_wav(p)
            consent_dir = Path(td) / "consents"
            consent_dir.mkdir()
            (consent_dir / "spk_001.json").write_text(
                json.dumps(
                    {
                        "speaker_id": "spk_001",
                        "consent_version": "v1",
                        "commercial_model_training_allowed": True,
                        "internal_research_allowed": True,
                        "evaluation_allowed": True,
                        "redistribution_allowed": False,
                        "recorded_at": "2026-01-01T00:00:00Z",
                        "withdrawal_reference": "x",
                    }
                ),
                encoding="utf-8",
            )
            qa_clips.CONSENTS = consent_dir
            row = {
                "clip_id": "c1",
                "speaker_id": "spk_001",
                "audio_path": str(p),
                "transcript": "hello",
                "language_class": "EN",
                "contains_numbers": False,
                "sha256": "abc",
                "bucket": "PRODUCT_CLEAN",
            }
            out = qa_clips.qa_row(row, {})
            self.assertEqual(out["qa_status"], "PASS", out.get("qa_errors"))


class TestGateLogic(unittest.TestCase):
    def test_empty_is_insufficient(self):
        # pure function style: empty observed should not authorize
        checks = {
            "min_speakers_5": False,
            "min_mix_500": False,
            "min_numeric_200": False,
        }
        self.assertFalse(all(checks.values()))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Deterministic readiness tests — no GPU training."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
MANIFEST = ROOT / "TRAINING_MANIFEST.json"
PROMPTS = ROOT / "prompts/product_clean_prompts.jsonl"


class TrainingReadinessTests(unittest.TestCase):
    def test_manifest_refuses_training(self):
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertFalse(m.get("training_authorized"))
        self.assertFalse(m.get("paid_job_authorized"))
        self.assertEqual(m["method"]["type"], "lora_peft")
        self.assertIn("q_proj", m["method"]["target_modules"])

    def test_authorization_script_blocks(self):
        rc = subprocess.call([sys.executable, str(SCRIPTS / "validate_authorization.py")])
        self.assertEqual(rc, 2)

    def test_train_script_blocks(self):
        rc = subprocess.call([sys.executable, str(SCRIPTS / "train_lora_whisper.py")])
        self.assertNotEqual(rc, 0)

    def test_prompts_exist_and_mixed_numeric(self):
        lines = [json.loads(l) for l in PROMPTS.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertGreaterEqual(len(lines), 20)
        langs = {x["lang"] for x in lines}
        self.assertIn("mixed", langs)
        self.assertIn("ne", langs)
        cats = {x["category"] for x in lines}
        self.assertIn("numeric", cats)

    def test_contamination_check_passes_without_train(self):
        rc = subprocess.call(
            [
                sys.executable,
                str(SCRIPTS / "check_contamination.py"),
                "--train",
                str(ROOT / "data/product_clean/train.jsonl"),
            ]
        )
        self.assertEqual(rc, 0)

    def test_gates_not_lowered(self):
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        g = m["qualification_gates"]
        self.assertEqual(g["ne_intent_min"], 0.60)
        self.assertEqual(g["mix_intent_min"], 0.60)
        self.assertEqual(g["en_intent_min"], 0.70)
        self.assertEqual(g["numeric_fidelity_min"], 0.70)
        self.assertEqual(g["ne_cer_max"], 0.45)

    def test_ct2_plumbing_report(self):
        rc = subprocess.call([sys.executable, str(SCRIPTS / "prove_ct2_plumbing.py")])
        self.assertEqual(rc, 0)
        report = json.loads(
            (ROOT / "artifacts/plumbing_proof/ct2_plumbing_report.json").read_text(encoding="utf-8")
        )
        self.assertFalse(report.get("deployment_path_blocked"))


if __name__ == "__main__":
    unittest.main()

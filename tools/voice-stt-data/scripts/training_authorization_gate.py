#!/usr/bin/env python3
"""V-NEXT-2B.6 training authorization gate.

Hard requirements (all must pass):
  >= 5 speakers (commercial consent)
  >= 500 clean MIX clips (PRODUCT_CLEAN + PASS)
  >= 200 clean numeric clips
  commercial consent complete
  zero RESEARCH_ONLY samples in TRAIN
  speaker-disjoint holdout exists
  QA pass rate acceptable (>= 0.90 of PRODUCT_CLEAN candidates or empty)
  contamination check clean
  dataset manifest present
  training manifest remains unauthorized until gate passes

Does NOT launch training.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
MANIFESTS = CORPUS / "manifests"
CONSENTS = CORPUS / "consents"
REPO = Path(__file__).resolve().parents[3]
TRAIN_MANIFEST = REPO / "tools" / "voice-stt-train" / "TRAINING_MANIFEST.json"

MIN_SPEAKERS = 5
MIN_MIX = 500
MIN_NUMERIC = 200
MIN_QA_PASS_RATE = 0.90


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=MANIFESTS / "dataset_manifest.jsonl")
    ap.add_argument("--stats", type=Path, default=MANIFESTS / "dataset_statistics.json")
    ap.add_argument("--split-report", type=Path, default=MANIFESTS / "split_report.json")
    ap.add_argument("--contamination", type=Path, default=MANIFESTS / "contamination_report.json")
    ap.add_argument("--qa-report", type=Path, default=MANIFESTS / "qa_report.json")
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--update-train-manifest", action="store_true")
    args = ap.parse_args()

    rows: list[dict] = []
    if args.manifest.exists():
        rows = [json.loads(l) for l in args.manifest.read_text(encoding="utf-8").splitlines() if l.strip()]

    clean_pass = [
        r
        for r in rows
        if r.get("bucket") == "PRODUCT_CLEAN" and r.get("qa_status") == "PASS"
    ]
    speakers = {r["speaker_id"] for r in clean_pass}
    mix = [r for r in clean_pass if r.get("language_class") == "MIX"]
    numeric = [r for r in clean_pass if r.get("contains_numbers")]
    research_in_train = [
        r
        for r in rows
        if r.get("bucket") == "RESEARCH_ONLY" and r.get("split") == "TRAIN"
    ]

    consents = []
    if CONSENTS.exists():
        for p in CONSENTS.glob("spk_*.json"):
            consents.append(json.loads(p.read_text(encoding="utf-8")))
    commercial = {
        c["speaker_id"]
        for c in consents
        if c.get("commercial_model_training_allowed") is True
    }
    commercial_speakers_with_clips = speakers & commercial

    split_ok = False
    speaker_disjoint = False
    if args.split_report.exists():
        sp = json.loads(args.split_report.read_text(encoding="utf-8"))
        speaker_disjoint = bool(sp.get("speaker_disjoint"))
        split_ok = bool(sp.get("training_split_ready"))

    contamination_clean = True
    if args.contamination.exists():
        cr = json.loads(args.contamination.read_text(encoding="utf-8"))
        contamination_clean = cr.get("status") == "CLEAN"
    elif rows:
        contamination_clean = False  # must run check when data exists

    qa_rate = 1.0
    if args.qa_report.exists():
        qr = json.loads(args.qa_report.read_text(encoding="utf-8"))
        total = int(qr.get("total") or 0)
        if total:
            qa_rate = float(qr.get("pass_rate") or 0.0)
    elif rows:
        n = len(rows)
        p = sum(1 for r in rows if r.get("qa_status") == "PASS")
        qa_rate = p / n if n else 0.0

    checks = {
        "min_speakers_5": len(commercial_speakers_with_clips) >= MIN_SPEAKERS,
        "min_mix_500": len(mix) >= MIN_MIX,
        "min_numeric_200": len(numeric) >= MIN_NUMERIC,
        "commercial_consent_complete": len(commercial_speakers_with_clips) >= MIN_SPEAKERS
        and all(r["speaker_id"] in commercial for r in clean_pass),
        "zero_research_only_in_train": len(research_in_train) == 0,
        "speaker_disjoint_holdout": speaker_disjoint and split_ok,
        "qa_pass_rate_ok": (not rows) or (qa_rate >= MIN_QA_PASS_RATE),
        "contamination_clean": contamination_clean if rows else True,
        "manifest_present": args.manifest.exists(),
        "human_verified_all_train": all(
            r.get("human_verified") for r in clean_pass if r.get("split") == "TRAIN"
        )
        if any(r.get("split") == "TRAIN" for r in clean_pass)
        else False,
    }

    # human_verified only required when we have train splits; if no train data, fail elsewhere
    if not any(r.get("split") == "TRAIN" for r in clean_pass):
        checks["human_verified_all_train"] = False

    all_ok = all(checks.values())
    if all_ok:
        verdict = "WHISPER_CS_LORA_TRAINING_AUTHORIZED"
    elif len(commercial_speakers_with_clips) == 0 and not rows:
        verdict = "PRODUCT_CLEAN_DATA_INSUFFICIENT_FOR_TRAINING"
    elif len(commercial_speakers_with_clips) < MIN_SPEAKERS and rows:
        # distinguish diversity vs pure empty
        if len(speakers) < MIN_SPEAKERS:
            verdict = "SPEAKER_DIVERSITY_INSUFFICIENT"
        else:
            verdict = "PRODUCT_SPEECH_CONSENT_INCOMPLETE"
    elif not contamination_clean:
        verdict = "PRODUCT_SPEECH_PROVENANCE_FAILED"
    elif rows and qa_rate < MIN_QA_PASS_RATE:
        verdict = "PRODUCT_SPEECH_QA_FAILED"
    else:
        verdict = "PRODUCT_CLEAN_DATA_INSUFFICIENT_FOR_TRAINING"

    report = {
        "mission": "V-NEXT-2B.6",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "training_authorized": all_ok,
        "paid_job_authorized": False,
        "thresholds": {
            "min_speakers": MIN_SPEAKERS,
            "min_mix": MIN_MIX,
            "min_numeric": MIN_NUMERIC,
            "min_qa_pass_rate": MIN_QA_PASS_RATE,
        },
        "observed": {
            "commercial_speakers_with_pass_clips": len(commercial_speakers_with_clips),
            "speakers": sorted(speakers),
            "clean_pass_clips": len(clean_pass),
            "mix_clean": len(mix),
            "numeric_clean": len(numeric),
            "research_only_in_train": len(research_in_train),
            "qa_pass_rate": qa_rate,
            "speaker_disjoint": speaker_disjoint,
            "split_ready": split_ok,
            "contamination_clean": contamination_clean,
        },
        "checks": checks,
        "dataset_version": None if not all_ok else "SAATHI_STT_PRODUCT_CORPUS_V1",
        "notes": (
            "Do not launch Hugging Face Jobs or local LoRA until WHISPER_CS_LORA_TRAINING_AUTHORIZED. "
            "Raw audio stays under ~/.saathi/stt-product-corpus/."
        ),
    }

    print(json.dumps(report, indent=2))
    print(verdict)

    out = args.report or (MANIFESTS / "training_authorization_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.update_train_manifest and TRAIN_MANIFEST.exists():
        tm = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
        tm["status"] = verdict
        tm["training_authorized"] = bool(all_ok)
        tm["paid_job_authorized"] = False
        tm["v_next_2b6_gate"] = {
            "checked_at": report["checked_at"],
            "verdict": verdict,
            "observed": report["observed"],
        }
        if all_ok:
            pc = tm.setdefault("datasets", {}).setdefault("product_clean", [])
            entry = str(CORPUS / "manifests" / "dataset_manifest.jsonl")
            if entry not in pc:
                pc.append(entry)
        else:
            # keep empty product_clean list when insufficient
            if "datasets" in tm:
                tm["datasets"]["product_clean"] = []
        TRAIN_MANIFEST.write_text(json.dumps(tm, indent=2) + "\n", encoding="utf-8")
        print("Updated", TRAIN_MANIFEST)

    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

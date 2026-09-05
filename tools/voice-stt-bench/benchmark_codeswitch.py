#!/usr/bin/env python3
"""
V-NEXT-2B.3 — Code-switch Whisper (CT2) benchmarks.

Gates locked in docs/voice-next-2b3/LOCKED_GATES.md BEFORE this script runs.
"""
from __future__ import annotations

import json
import re
import resource
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
RESULTS = ROOT / "results" / "v-next-2b3"
RESULTS.mkdir(parents=True, exist_ok=True)

# LOCKED — do not modify after observing results
GATES = {
    "ne_intent_min": 0.60,
    "ne_first_span_min": 0.50,
    "ne_cer_max": 0.45,
    "mix_intent_min": 0.60,
    "mix_first_span_min": 0.50,
    "mix_term_min": 0.50,
    "mix_cer_max": 0.50,
    "en_intent_min": 0.70,  # for universal primary
    "numeric_fidelity_min": 0.70,
    "peak_rss_mib_max": 1500,
}

SAATHI_TERMS = [
    "saathi", "saathios", "portfolio", "risk", "nav", "drawdown", "rebalance",
    "exposure", "trading guardian", "executiongateway", "approvals", "missions",
    "command center", "stop-loss", "ollama",
]

# Numbers we expect in numeric set (normalized forms)
NUMERIC_TARGETS = {
    "nm_001": ["5", "five", "percent"],
    "nm_002": ["15", "fifteen", "percent", "stop"],
    "nm_003": ["500", "five hundred", "shares", "hundred"],
    "nm_004": ["50", "50000", "fifty", "thousand", "npr"],
    "nm_005": ["1.5", "1 point 5", "one point five", "percent"],
    "nm_006": ["5", "five", "percent", "drawdown"],
    "nm_007": ["500", "पाँच", "सय", "shares"],
}


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower().strip()
    s = re.sub(r"[^\w\s\u0900-\u097F.]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
    return s


def cer(ref: str, hyp: str) -> float:
    r = normalize_text(ref).replace(" ", "")
    h = normalize_text(hyp).replace(" ", "")
    if not r:
        return 0.0 if not h else 1.0
    dp = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        prev = dp[0]
        dp[0] = i
        for j, hc in enumerate(h, 1):
            cur = dp[j]
            dp[j] = prev if rc == hc else 1 + min(prev, dp[j], dp[j - 1])
            prev = cur
    return dp[-1] / max(1, len(r))


def wer(ref: str, hyp: str) -> float:
    try:
        from jiwer import wer as jwer

        r, h = normalize_text(ref), normalize_text(hyp)
        if not r:
            return 0.0 if not h else 1.0
        return float(jwer(r, h))
    except Exception:
        rt, ht = normalize_text(ref).split(), normalize_text(hyp).split()
        if not rt:
            return 0.0 if not ht else 1.0
        return 1.0 - len(set(rt) & set(ht)) / len(set(rt))


def intent_ok(ref: str, hyp: str) -> bool:
    rt = [t for t in normalize_text(ref).split() if len(t) > 2]
    if not rt:
        return normalize_text(ref) == normalize_text(hyp)
    ht = set(normalize_text(hyp).split())
    return (sum(1 for t in rt if t in ht) / len(rt)) >= 0.5


def first_span_ok(ref: str, hyp: str) -> bool:
    rt, ht = normalize_text(ref).split(), normalize_text(hyp).split()
    if not rt:
        return True
    return bool(ht) and ht[0] == rt[0]


def term_hits(ref: str, hyp: str) -> tuple[int, int]:
    r, h = normalize_text(ref), normalize_text(hyp)
    present = [t for t in SAATHI_TERMS if t in r]
    if not present:
        return 0, 0
    return sum(1 for t in present if t in h), len(present)


def numeric_fidelity(item_id: str, hyp: str) -> float | None:
    targets = NUMERIC_TARGETS.get(item_id)
    if not targets:
        return None
    h = normalize_text(hyp)
    hits = sum(1 for t in targets if t in h)
    return hits / len(targets)


def rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def load_items():
    items = []
    # Locked 2B.1 corpus
    m1 = CORPUS / "manifest.json"
    if m1.exists():
        for it in json.loads(m1.read_text(encoding="utf-8"))["items"]:
            if it.get("wav"):
                items.append({**it, "corpus": "locked_2b1"})
    # Code-switch + numeric
    m2 = CORPUS / "codeswitch" / "manifest.json"
    if m2.exists():
        for it in json.loads(m2.read_text(encoding="utf-8"))["items"]:
            if it.get("wav"):
                items.append({**it, "corpus": "codeswitch_2b3"})
    # Owner corpus if present
    m3 = Path.home() / ".saathi/stt-owner-corpus/manifest.json"
    if m3.exists():
        for it in json.loads(m3.read_text(encoding="utf-8"))["items"]:
            if it.get("wav") and Path(it["wav"]).exists():
                items.append({**it, "corpus": "owner_real"})
    return items


def summarize(group):
    if not group:
        return None
    return {
        "n": len(group),
        "mean_wer": sum(x["wer"] for x in group) / len(group),
        "mean_cer": sum(x["cer"] for x in group) / len(group),
        "intent_rate": sum(1 for x in group if x["intent_ok"]) / len(group),
        "first_span_rate": sum(1 for x in group if x["first_span_ok"]) / len(group),
        "term_preservation": (
            sum(x["term_hits"] for x in group) / sum(x["term_total"] for x in group)
            if sum(x["term_total"] for x in group)
            else None
        ),
    }


def pct(vals):
    if not vals:
        return None
    s = sorted(vals)

    def q(p):
        if len(s) < 3 and p > 50:
            return s[-1]
        return s[int(round((p / 100) * (len(s) - 1)))]

    return {"p50": q(50), "p95": q(95) if len(s) >= 3 else s[-1], "worst": s[-1], "n": len(s)}


def run_candidate(name: str, model_path: str, items: list, language_mode: str = "auto"):
    from faster_whisper import WhisperModel

    print(f"\n=== {name} lang={language_mode} ===")
    t0 = time.perf_counter()
    model = WhisperModel(model_path, device="cpu", compute_type="int8")
    load_s = time.perf_counter() - t0
    print(f"cold {load_s:.2f}s rss={rss_mib():.0f}")

    rows = []
    decode_times = []
    for it in items:
        wav = Path(it["wav"]) if Path(it["wav"]).is_absolute() else CORPUS / it["wav"]
        if not wav.exists():
            continue
        lang = it.get("lang")
        if language_mode == "auto":
            lang_arg = None
        elif language_mode == "ne":
            lang_arg = "ne"
        elif language_mode == "en":
            lang_arg = "en"
        else:
            lang_arg = None

        t1 = time.perf_counter()
        segments, info = model.transcribe(str(wav), language=lang_arg, beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        decode_s = time.perf_counter() - t1
        decode_times.append(decode_s)
        ref = it["text"]
        th, tt = term_hits(ref, text)
        nf = numeric_fidelity(it["id"], text)
        row = {
            "id": it["id"],
            "corpus": it.get("corpus"),
            "category": it.get("category"),
            "lang": lang,
            "ref": ref,
            "hyp": text,
            "wer": wer(ref, text),
            "cer": cer(ref, text),
            "intent_ok": intent_ok(ref, text),
            "first_span_ok": first_span_ok(ref, text),
            "term_hits": th,
            "term_total": tt,
            "numeric_fidelity": nf,
            "decode_s": decode_s,
            "detected_language": getattr(info, "language", None),
            # diagnostic flags
            "hyp_has_devanagari": bool(re.search(r"[\u0900-\u097F]", text)),
            "hyp_has_latin": bool(re.search(r"[A-Za-z]", text)),
            "ref_has_devanagari": bool(re.search(r"[\u0900-\u097F]", ref)),
            "ref_has_latin": bool(re.search(r"[A-Za-z]", ref)),
        }
        rows.append(row)
        print(f"  {it['id']}: intent={row['intent_ok']} CER={row['cer']:.2f} | {text[:80]!r}")

    # Groups
    by_lang = defaultdict(list)
    by_cat = defaultdict(list)
    by_corpus = defaultdict(list)
    for r in rows:
        by_lang[r["lang"]].append(r)
        by_cat[r["category"] or "UNK"].append(r)
        by_corpus[r["corpus"] or "UNK"].append(r)

    ne_rows = [r for r in rows if r["lang"] == "ne" or r["category"] == "NE_CMD"]
    mix_rows = [
        r
        for r in rows
        if r["lang"] == "mixed"
        or r["category"] in ("MIX", "MIX_CS")
        or (r["corpus"] == "codeswitch_2b3" and r["lang"] == "mixed")
    ]
    en_rows = [r for r in rows if r["lang"] == "en" and r["category"] not in ("NUMERIC",)]
    # expand EN: all pure en from locked + non-numeric
    en_rows = [r for r in rows if r["lang"] == "en"]
    num_rows = [r for r in rows if r["category"] == "NUMERIC" or r["id"].startswith("nm_")]

    ne_sum = summarize(ne_rows)
    mix_sum = summarize(mix_rows)
    en_sum = summarize(en_rows)

    num_scores = [r["numeric_fidelity"] for r in num_rows if r["numeric_fidelity"] is not None]
    num_fid = sum(num_scores) / len(num_scores) if num_scores else None

    # Gate evaluation
    ne_gate = {
        "intent_ok": ne_sum and ne_sum["intent_rate"] >= GATES["ne_intent_min"],
        "first_span_ok": ne_sum and ne_sum["first_span_rate"] >= GATES["ne_first_span_min"],
        "cer_ok": ne_sum and ne_sum["mean_cer"] <= GATES["ne_cer_max"],
    }
    ne_gate["passed"] = all(ne_gate.values()) if ne_sum else False

    mix_gate = {
        "intent_ok": mix_sum and mix_sum["intent_rate"] >= GATES["mix_intent_min"],
        "first_span_ok": mix_sum and mix_sum["first_span_rate"] >= GATES["mix_first_span_min"],
        "term_ok": mix_sum
        and (
            mix_sum["term_preservation"] is None
            or mix_sum["term_preservation"] >= GATES["mix_term_min"]
        ),
        "cer_ok": mix_sum and mix_sum["mean_cer"] <= GATES["mix_cer_max"],
    }
    mix_gate["passed"] = all(mix_gate.values()) if mix_sum else False

    en_ok = en_sum and en_sum["intent_rate"] >= GATES["en_intent_min"]
    num_ok = num_fid is not None and num_fid >= GATES["numeric_fidelity_min"]
    rss = rss_mib()
    resource_ok = rss <= GATES["peak_rss_mib_max"]

    universal = ne_gate["passed"] and mix_gate["passed"] and en_ok and resource_ok

    classification = "NOT_QUALIFIED"
    if universal and (num_ok or num_fid is None):
        classification = "UNIVERSAL_PRIMARY_QUALIFIED"
    elif en_ok and not ne_gate["passed"] and not mix_gate["passed"]:
        classification = "ENGLISH_ONLY_QUALIFIED"
    elif ne_gate["passed"] and not mix_gate["passed"]:
        classification = "NEPALI_ONLY_QUALIFIED"
    elif mix_gate["passed"] and not ne_gate["passed"]:
        classification = "MIXED_ONLY_PARTIAL"
    elif not resource_ok:
        classification = "RESOURCE_BLOCKED"

    out = {
        "candidate": name,
        "model_path": model_path,
        "language_mode": language_mode,
        "gates_locked": GATES,
        "cold_load_s": load_s,
        "peak_rss_mib": rss,
        "latency": pct(decode_times),
        "by_language": {k: summarize(v) for k, v in by_lang.items()},
        "by_category": {k: summarize(v) for k, v in by_cat.items()},
        "by_corpus": {k: summarize(v) for k, v in by_corpus.items()},
        "ne_metrics": ne_sum,
        "mix_metrics": mix_sum,
        "en_metrics": en_sum,
        "numeric_fidelity_mean": num_fid,
        "ne_gate": ne_gate,
        "mix_gate": mix_gate,
        "en_intent_ok": en_ok,
        "numeric_ok": num_ok,
        "resource_ok": resource_ok,
        "universal_primary": universal,
        "classification": classification,
        "rows": rows,
    }
    path = RESULTS / f"{name.replace('/', '_')}_{language_mode}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path} classification={classification}")
    print(f"  NE gate={ne_gate['passed']} MIX gate={mix_gate['passed']} EN_ok={en_ok} num={num_fid}")
    return out


def main():
    import os

    items = load_items()
    if not items:
        print("No items")
        return 1
    print(f"Loaded {len(items)} items")

    root = Path.home() / ".saathi/stt-models/v-next-2b3"
    cands = []
    for p in sorted(root.glob("*-ct2")):
        if (p / "model.bin").exists():
            cands.append((p.name, str(p)))
    extra = os.environ.get("STT_CS_MODELS", "")
    for part in extra.split(","):
        if part.strip():
            cands.append((Path(part.strip()).name, part.strip()))

    if not cands:
        print("No CT2 models in", root)
        return 2

    results = []
    for name, path in cands:
        try:
            # Primary experiment: auto language (critical for code-switch)
            results.append(run_candidate(name, path, items, "auto"))
        except Exception as e:
            print("FAIL", name, e)
            results.append({"candidate": name, "error": str(e)})

    summary = {
        "mission": "V-NEXT-2B.3",
        "gates": GATES,
        "candidates": [
            {
                "name": r.get("candidate"),
                "error": r.get("error"),
                "classification": r.get("classification"),
                "ne_gate": r.get("ne_gate"),
                "mix_gate": r.get("mix_gate"),
                "en_metrics": r.get("en_metrics"),
                "ne_metrics": r.get("ne_metrics"),
                "mix_metrics": r.get("mix_metrics"),
                "numeric_fidelity_mean": r.get("numeric_fidelity_mean"),
                "peak_rss_mib": r.get("peak_rss_mib"),
                "latency": r.get("latency"),
                "cold_load_s": r.get("cold_load_s"),
            }
            for r in results
        ],
    }
    (RESULTS / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

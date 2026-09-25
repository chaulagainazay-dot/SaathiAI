#!/usr/bin/env python3
"""V-NEXT-2B.4 — Whisper CS Small (historical) vs Omnilingual CTC-300M on locked corpus."""
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
RESULTS = ROOT / "results" / "v-next-2b4"
RESULTS.mkdir(parents=True, exist_ok=True)

# Locked gates (do not lower)
GATES = {
    "en_intent_min": 0.70,
    "ne_intent_min": 0.60,
    "mix_intent_min": 0.60,
    "ne_first_span_min": 0.50,
    "ne_cer_max": 0.45,
    "numeric_fidelity_min": 0.70,
}

SAATHI_TERMS = [
    "saathi", "portfolio", "risk", "nav", "drawdown", "rebalance", "exposure",
    "trading guardian", "executiongateway", "approvals", "missions", "stop",
]
NUMERIC_TARGETS = {
    "nm_001": ["5", "five", "percent"],
    "nm_002": ["15", "fifteen", "percent", "stop"],
    "nm_003": ["500", "five hundred", "shares", "hundred"],
    "nm_004": ["50", "50000", "fifty", "thousand", "npr"],
    "nm_005": ["1.5", "one point five", "percent"],
    "nm_006": ["5", "five", "percent", "drawdown"],
    "nm_007": ["500", "shares", "पाँच", "सय"],
}


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower().strip()
    s = re.sub(r"[^\w\s\u0900-\u097F.]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s.translate(str.maketrans("०१२३४५६७८९", "0123456789"))


def cer(ref, hyp):
    r, h = normalize_text(ref).replace(" ", ""), normalize_text(hyp).replace(" ", "")
    if not r:
        return 0.0 if not h else 1.0
    dp = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        prev, dp[0] = dp[0], i
        for j, hc in enumerate(h, 1):
            cur = dp[j]
            dp[j] = prev if rc == hc else 1 + min(prev, dp[j], dp[j - 1])
            prev = cur
    return dp[-1] / max(1, len(r))


def wer(ref, hyp):
    try:
        from jiwer import wer as jwer
        r, h = normalize_text(ref), normalize_text(hyp)
        return 0.0 if not r and not h else (1.0 if not r else float(jwer(r, h)))
    except Exception:
        rt, ht = set(normalize_text(ref).split()), set(normalize_text(hyp).split())
        return 1.0 - (len(rt & ht) / len(rt) if rt else 0.0)


def intent_ok(ref, hyp):
    rt = [t for t in normalize_text(ref).split() if len(t) > 2]
    if not rt:
        return normalize_text(ref) == normalize_text(hyp)
    ht = set(normalize_text(hyp).split())
    return sum(1 for t in rt if t in ht) / len(rt) >= 0.5


def first_span_ok(ref, hyp):
    rt, ht = normalize_text(ref).split(), normalize_text(hyp).split()
    return (not rt) or (bool(ht) and ht[0] == rt[0])


def term_hits(ref, hyp):
    r, h = normalize_text(ref), normalize_text(hyp)
    present = [t for t in SAATHI_TERMS if t in r]
    if not present:
        return 0, 0
    return sum(1 for t in present if t in h), len(present)


def numeric_fidelity(iid, hyp):
    targets = NUMERIC_TARGETS.get(iid)
    if not targets:
        return None
    h = normalize_text(hyp)
    return sum(1 for t in targets if t in h) / len(targets)


def rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def load_items():
    items = []
    for mf, key in [
        (CORPUS / "manifest.json", "locked_2b1"),
        (CORPUS / "codeswitch" / "manifest.json", "codeswitch_2b3"),
    ]:
        if not mf.exists():
            continue
        for it in json.loads(mf.read_text(encoding="utf-8"))["items"]:
            if not it.get("wav"):
                continue
            wav = CORPUS / it["wav"] if not Path(it["wav"]).is_absolute() else Path(it["wav"])
            if wav.exists():
                items.append({**it, "corpus": key, "wav_path": str(wav)})
    # owner
    om = Path.home() / ".saathi/stt-owner-corpus/manifest.json"
    if om.exists():
        for it in json.loads(om.read_text(encoding="utf-8"))["items"]:
            if it.get("status") == "SPEECH_DETECTED" and it.get("wav") and Path(it["wav"]).exists():
                items.append({**it, "corpus": "owner_real", "wav_path": it["wav"]})
    return items


def summarize(rows):
    if not rows:
        return None
    th = sum(r["term_hits"] for r in rows)
    tt = sum(r["term_total"] for r in rows)
    return {
        "n": len(rows),
        "mean_wer": sum(r["wer"] for r in rows) / len(rows),
        "mean_cer": sum(r["cer"] for r in rows) / len(rows),
        "intent_rate": sum(1 for r in rows if r["intent_ok"]) / len(rows),
        "first_span_rate": sum(1 for r in rows if r["first_span_ok"]) / len(rows),
        "term_preservation": (th / tt) if tt else None,
    }


def pct(vals):
    if not vals:
        return None
    s = sorted(vals)
    def q(p):
        return s[int(round((p / 100) * (len(s) - 1)))]
    return {"p50": q(50), "p95": q(95) if len(s) >= 3 else s[-1], "worst": s[-1], "n": len(s)}


def score_rows(rows):
    ne = [r for r in rows if r["lang"] == "ne" or r.get("category") == "NE_CMD"]
    mix = [r for r in rows if r["lang"] == "mixed" or r.get("category") in ("MIX", "MIX_CS")]
    en = [r for r in rows if r["lang"] == "en"]
    num = [r for r in rows if r.get("category") == "NUMERIC" or str(r["id"]).startswith("nm_")]
    owner = [r for r in rows if r.get("corpus") == "owner_real"]
    ne_s, mix_s, en_s = summarize(ne), summarize(mix), summarize(en)
    num_scores = [r["numeric_fidelity"] for r in num if r.get("numeric_fidelity") is not None]
    num_fid = sum(num_scores) / len(num_scores) if num_scores else None
    gates = {
        "en_ok": en_s and en_s["intent_rate"] >= GATES["en_intent_min"],
        "ne_intent_ok": ne_s and ne_s["intent_rate"] >= GATES["ne_intent_min"],
        "ne_first_ok": ne_s and ne_s["first_span_rate"] >= GATES["ne_first_span_min"],
        "ne_cer_ok": ne_s and ne_s["mean_cer"] <= GATES["ne_cer_max"],
        "mix_ok": mix_s and mix_s["intent_rate"] >= GATES["mix_intent_min"],
        "numeric_ok": num_fid is not None and num_fid >= GATES["numeric_fidelity_min"],
    }
    gates["ne_passed"] = all([gates["ne_intent_ok"], gates["ne_first_ok"], gates["ne_cer_ok"]])
    gates["universal"] = gates["en_ok"] and gates["ne_passed"] and gates["mix_ok"] and gates["numeric_ok"]
    return {
        "en": en_s, "ne": ne_s, "mix": mix_s, "owner": summarize(owner),
        "numeric_fidelity_mean": num_fid, "gates": gates,
    }


def run_omni(items):
    from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

    t0 = time.perf_counter()
    pipe = ASRInferencePipeline(model_card="omniASR_CTC_300M")
    load_s = time.perf_counter() - t0
    rows = []
    times = []
    for it in items:
        # Language policy: auto/unconditioned for mixed; eng_Latn / nep_Deva for pure
        lang = it.get("lang")
        if lang == "en":
            lang_ids = ["eng_Latn"]
        elif lang == "ne":
            lang_ids = ["nep_Deva"]
        else:
            # code-switch: try nep_Deva as primary SaathiOS NE-first mixed
            lang_ids = ["nep_Deva"]
        t1 = time.perf_counter()
        try:
            texts = pipe.transcribe([it["wav_path"]], lang=lang_ids, batch_size=1)
            hyp = texts[0] if texts else ""
        except Exception as e:
            hyp = f"__ERROR__{e}"
        dt = time.perf_counter() - t1
        times.append(dt)
        th, tt = term_hits(it["text"], hyp)
        rows.append({
            "id": it["id"], "corpus": it.get("corpus"), "category": it.get("category"),
            "lang": lang, "ref": it["text"], "hyp": hyp,
            "wer": wer(it["text"], hyp), "cer": cer(it["text"], hyp),
            "intent_ok": intent_ok(it["text"], hyp),
            "first_span_ok": first_span_ok(it["text"], hyp),
            "term_hits": th, "term_total": tt,
            "numeric_fidelity": numeric_fidelity(it["id"], hyp),
            "decode_s": dt,
            "hyp_has_devanagari": bool(re.search(r"[\u0900-\u097F]", hyp)),
            "hyp_has_latin": bool(re.search(r"[A-Za-z]", hyp)),
        })
        print(f"  {it['id']}: intent={rows[-1]['intent_ok']} CER={rows[-1]['cer']:.2f} | {hyp[:70]!r}")
    scored = score_rows(rows)
    out = {
        "candidate": "omniASR-CTC-300M",
        "cold_load_s": load_s,
        "peak_rss_mib": rss(),
        "latency": pct(times),
        **scored,
        "rows": rows,
    }
    path = RESULTS / "omniASR-CTC-300M.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote", path, "gates", scored["gates"])
    return out


def load_whisper_historical():
    """Load V-NEXT-2B.3 bijay-small results as champion control (do not re-run)."""
    p = Path("/Users/macbookpro/SaathiAI-voice-next-2b3/tools/voice-stt-bench/results/v-next-2b3/bijay-small-ne-en-v3.1-ct2_auto.json")
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return {
        "candidate": "bijay-small-ne-en-v3.1 (historical 2B.3)",
        "source": str(p),
        "cold_load_s": d.get("cold_load_s"),
        "peak_rss_mib": d.get("peak_rss_mib"),
        "latency": d.get("latency"),
        "en": d.get("en_metrics"),
        "ne": d.get("ne_metrics"),
        "mix": d.get("mix_metrics"),
        "numeric_fidelity_mean": d.get("numeric_fidelity_mean"),
        "classification": d.get("classification"),
        "note": "Historical control — not re-run",
    }


def main():
    items = load_items()
    print(f"items={len(items)}")
    whisper = load_whisper_historical()
    omni = run_omni(items)
    comparison = {
        "mission": "V-NEXT-2B.4",
        "gates": GATES,
        "whisper_cs_small": whisper,
        "omnilingual_ctc_300m": {
            "candidate": omni["candidate"],
            "cold_load_s": omni["cold_load_s"],
            "peak_rss_mib": omni["peak_rss_mib"],
            "latency": omni["latency"],
            "en": omni["en"],
            "ne": omni["ne"],
            "mix": omni["mix"],
            "owner": omni["owner"],
            "numeric_fidelity_mean": omni["numeric_fidelity_mean"],
            "gates": omni["gates"],
        },
    }
    # Winner heuristic
    w_en = (whisper or {}).get("en", {}) or {}
    o_en = omni["en"] or {}
    w_ne = (whisper or {}).get("ne", {}) or {}
    o_ne = omni["ne"] or {}
    w_mix = (whisper or {}).get("mix", {}) or {}
    o_mix = omni["mix"] or {}
    comparison["head_to_head"] = {
        "en_intent": {"whisper": w_en.get("intent_rate"), "omni": o_en.get("intent_rate")},
        "ne_intent": {"whisper": w_ne.get("intent_rate"), "omni": o_ne.get("intent_rate")},
        "mix_intent": {"whisper": w_mix.get("intent_rate"), "omni": o_mix.get("intent_rate")},
        "numeric": {
            "whisper": (whisper or {}).get("numeric_fidelity_mean"),
            "omni": omni["numeric_fidelity_mean"],
        },
        "rss": {
            "whisper": (whisper or {}).get("peak_rss_mib"),
            "omni": omni["peak_rss_mib"],
        },
    }
    (RESULTS / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(comparison["head_to_head"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

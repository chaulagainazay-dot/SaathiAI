#!/usr/bin/env python3
"""Benchmark local Whisper STT candidates on the evaluation corpus."""
from __future__ import annotations

import json
import os
import re
import resource
import subprocess
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

# Locked before measurement (must not be lowered post-hoc)
NEPALI_GATES = {
    "intent_preservation_min": 0.60,
    "first_span_preservation_min": 0.50,
    "cer_max": 0.45,
    "term_preservation_min": 0.40,
}

SAATHI_TERMS = [
    "saathi",
    "portfolio",
    "risk",
    "nav",
    "drawdown",
    "rebalance",
    "exposure",
    "trading guardian",
    "executiongateway",
    "approvals",
    "missions",
    "command center",
]


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower().strip()
    s = re.sub(r"[^\w\s\u0900-\u097F]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def cer(ref: str, hyp: str) -> float:
    r = normalize_text(ref).replace(" ", "")
    h = normalize_text(hyp).replace(" ", "")
    if not r:
        return 0.0 if not h else 1.0
    # Levenshtein
    dp = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        prev = dp[0]
        dp[0] = i
        for j, hc in enumerate(h, 1):
            cur = dp[j]
            if rc == hc:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = cur
    return dp[-1] / max(1, len(r))


def wer(ref: str, hyp: str) -> float:
    try:
        from jiwer import wer as jwer

        r = normalize_text(ref)
        h = normalize_text(hyp)
        if not r:
            return 0.0 if not h else 1.0
        return float(jwer(r, h))
    except Exception:
        # token-level fallback
        rt = normalize_text(ref).split()
        ht = normalize_text(hyp).split()
        if not rt:
            return 0.0 if not ht else 1.0
        # simple set overlap inverse as crude proxy
        return 1.0 - (len(set(rt) & set(ht)) / len(set(rt)))


def intent_preserved(ref: str, hyp: str) -> bool:
    """Heuristic: ≥50% of content tokens appear in hypothesis (latin or devanagari)."""
    rt = [t for t in normalize_text(ref).split() if len(t) > 2]
    if not rt:
        return normalize_text(ref) == normalize_text(hyp)
    ht = set(normalize_text(hyp).split())
    hits = sum(1 for t in rt if t in ht)
    return (hits / len(rt)) >= 0.5


def first_span_ok(ref: str, hyp: str) -> bool:
    rt = normalize_text(ref).split()
    ht = normalize_text(hyp).split()
    if not rt:
        return True
    return bool(ht) and ht[0] == rt[0]


def term_hits(ref: str, hyp: str) -> tuple[int, int]:
    r = normalize_text(ref)
    h = normalize_text(hyp)
    present = [t for t in SAATHI_TERMS if t in r]
    if not present:
        return 0, 0
    hits = sum(1 for t in present if t in h)
    return hits, len(present)


def rss_mib() -> float:
    # macOS: ru_maxrss is bytes
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def load_manifest():
    path = CORPUS / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [i for i in data["items"] if i.get("wav")]


def transcribe_faster_whisper(model_size: str, wav: Path, language: str | None):
    from faster_whisper import WhisperModel

    # int8 for 8GB host
    t0 = time.perf_counter()
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    load_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    lang = None if language in (None, "mixed", "auto") else language
    segments, info = model.transcribe(str(wav), language=lang, beam_size=1, vad_filter=True)
    text = " ".join(s.text.strip() for s in segments).strip()
    decode_s = time.perf_counter() - t1
    return {
        "text": text,
        "load_s": load_s,
        "decode_s": decode_s,
        "detected_language": getattr(info, "language", None),
        "rss_mib": rss_mib(),
    }


def transcribe_whisper_cpp(bin_path: str, model_path: str, wav: Path, language: str | None):
    lang = language if language in ("en", "ne") else "auto"
    cmd = [bin_path, "-m", model_path, "-f", str(wav), "-nt", "-np"]
    if lang != "auto":
        cmd += ["-l", lang]
    t0 = time.perf_counter()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    elapsed = time.perf_counter() - t0
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    # whisper-cli prints transcript lines; take last non-empty non-log line
    lines = [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.startswith("[")]
    text = lines[-1] if lines else ""
    return {"text": text, "load_s": None, "decode_s": elapsed, "detected_language": lang, "rss_mib": None}


def run_candidate(name: str, model_size: str, items: list, engine: str = "faster-whisper"):
    print(f"\n=== {name} ({engine}/{model_size}) ===")
    # Preload once for fair warm timings
    model = None
    load_s = None
    if engine == "faster-whisper":
        from faster_whisper import WhisperModel

        t0 = time.perf_counter()
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        load_s = time.perf_counter() - t0
        print(f"cold load {load_s:.2f}s rss≈{rss_mib():.0f} MiB")

    rows = []
    decode_times = []
    for it in items:
        wav = CORPUS / it["wav"]
        if not wav.exists():
            continue
        lang = it.get("lang")
        t1 = time.perf_counter()
        if engine == "faster-whisper":
            lang_arg = None if lang in (None, "mixed") else ("ne" if lang == "ne" else "en" if lang == "en" else None)
            segments, info = model.transcribe(str(wav), language=lang_arg, beam_size=1, vad_filter=True)
            text = " ".join(s.text.strip() for s in segments).strip()
            decode_s = time.perf_counter() - t1
            det = getattr(info, "language", None)
        else:
            raise ValueError(engine)
        decode_times.append(decode_s)
        ref = it["text"]
        w = wer(ref, text)
        c = cer(ref, text)
        intent = intent_preserved(ref, text)
        first = first_span_ok(ref, text)
        th, tt = term_hits(ref, text)
        rows.append(
            {
                "id": it["id"],
                "category": it["category"],
                "lang": lang,
                "ref": ref,
                "hyp": text,
                "wer": w,
                "cer": c,
                "intent_ok": intent,
                "first_span_ok": first,
                "term_hits": th,
                "term_total": tt,
                "decode_s": decode_s,
                "detected_language": det,
            }
        )
        print(f"  {it['id']}: WER={w:.2f} CER={c:.2f} intent={intent} | {text[:80]!r}")

    def pct(vals):
        if not vals:
            return None
        s = sorted(vals)
        def q(p):
            if len(s) < 3 and p > 50:
                return s[-1]
            idx = int(round((p / 100) * (len(s) - 1)))
            return s[idx]
        return {"p50": q(50), "p95": q(95) if len(s) >= 3 else s[-1], "worst": s[-1], "n": len(s)}

    by_cat = defaultdict(list)
    by_lang = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
        by_lang[r["lang"]].append(r)

    def summarize(group):
        if not group:
            return None
        intents = [1 if x["intent_ok"] else 0 for x in group]
        cers = [x["cer"] for x in group]
        wers = [x["wer"] for x in group]
        firsts = [1 if x["first_span_ok"] else 0 for x in group]
        th = sum(x["term_hits"] for x in group)
        tt = sum(x["term_total"] for x in group)
        return {
            "n": len(group),
            "mean_wer": sum(wers) / len(wers),
            "mean_cer": sum(cers) / len(cers),
            "intent_rate": sum(intents) / len(intents),
            "first_span_rate": sum(firsts) / len(firsts),
            "term_preservation": (th / tt) if tt else None,
        }

    # Nepali gate evaluation on NE_CMD + MIX
    ne_rows = [r for r in rows if r["category"] in ("NE_CMD", "MIX") or r["lang"] in ("ne", "mixed")]
    ne_sum = summarize(ne_rows)
    gate = {
        "intent_ok": ne_sum and ne_sum["intent_rate"] >= NEPALI_GATES["intent_preservation_min"],
        "first_span_ok": ne_sum and ne_sum["first_span_rate"] >= NEPALI_GATES["first_span_preservation_min"],
        "cer_ok": ne_sum and ne_sum["mean_cer"] <= NEPALI_GATES["cer_max"],
        "term_ok": True
        if not ne_sum or ne_sum["term_preservation"] is None
        else ne_sum["term_preservation"] >= NEPALI_GATES["term_preservation_min"],
    }
    gate["passed"] = all(gate.values())

    out = {
        "candidate": name,
        "engine": engine,
        "model": model_size,
        "cold_load_s": load_s,
        "peak_rss_mib": rss_mib(),
        "latency_decode_s": pct(decode_times),
        "by_language": {k: summarize(v) for k, v in by_lang.items()},
        "by_category": {k: summarize(v) for k, v in by_cat.items()},
        "nepali_gate": {"criteria": NEPALI_GATES, "metrics": ne_sum, "result": gate},
        "rows": rows,
    }
    path = RESULTS / f"{name.replace(' ', '_')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path}")
    print(f"Nepali gate passed={gate['passed']} metrics={ne_sum}")
    return out


def main():
    items = load_manifest()
    if not items:
        print("No corpus items; run generate_corpus.py first", file=sys.stderr)
        return 1

    sizes = os.environ.get("STT_MODELS", "tiny,base").split(",")
    results = []
    for size in sizes:
        size = size.strip()
        if not size:
            continue
        try:
            results.append(run_candidate(f"faster-whisper-{size}", size, items))
        except Exception as e:
            print(f"FAILED {size}: {e}", file=sys.stderr)
            results.append({"candidate": f"faster-whisper-{size}", "error": str(e)})

    summary = {
        "host": "Apple M2 8GB",
        "nepali_gates": NEPALI_GATES,
        "candidates": [
            {
                "name": r.get("candidate"),
                "error": r.get("error"),
                "nepali_gate_passed": (r.get("nepali_gate") or {}).get("result", {}).get("passed"),
                "by_language": r.get("by_language"),
                "latency": r.get("latency_decode_s"),
                "peak_rss_mib": r.get("peak_rss_mib"),
                "cold_load_s": r.get("cold_load_s"),
            }
            for r in results
        ],
    }
    (RESULTS / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

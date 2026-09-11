#!/usr/bin/env python3
"""
V-NEXT-2B.2 — Benchmark Nepali-specialized Whisper (CT2/faster-whisper).

Locked gates from V-NEXT-2B.1 (DO NOT LOWER):
  intent >= 0.60, first-span >= 0.50, CER <= 0.45
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
RESULTS = ROOT / "results" / "v-next-2b2"
RESULTS.mkdir(parents=True, exist_ok=True)

# LOCKED — identical to V-NEXT-2B.1
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

# Bounded deterministic domain repairs (applied only in NORMALIZED metrics path)
DOMAIN_VOCAB = {
    r"\bsafi\b": "saathi",
    r"\bsathy\b": "saathi",
    r"\bsophie\b": "saathi",
    r"\bsoffie\b": "saathi",
    r"\bexecution gateway\b": "executiongateway",
    r"\btrading through\b": "trading guardian",
    r"\bporfali\b": "portfolio",
    r"\bpork folio\b": "portfolio",
    r"\bport folio\b": "portfolio",
    r"\breport folio\b": "portfolio",
    r"\bdraw down\b": "drawdown",
    r"\bprovals\b": "approvals",
    r"\bproofles\b": "approvals",
}


def normalize_text(s: str, domain: bool = False) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower().strip()
    s = re.sub(r"[^\w\s\u0900-\u097F]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    # Nepali digits → ASCII for measurement only
    trans = str.maketrans("०१२३४५६७८९", "0123456789")
    s = s.translate(trans)
    if domain:
        for pat, rep in DOMAIN_VOCAB.items():
            s = re.sub(pat, rep, s, flags=re.I)
    return s


def cer(ref: str, hyp: str, domain: bool = False) -> float:
    r = normalize_text(ref, domain).replace(" ", "")
    h = normalize_text(hyp, domain).replace(" ", "")
    if not r:
        return 0.0 if not h else 1.0
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


def wer(ref: str, hyp: str, domain: bool = False) -> float:
    try:
        from jiwer import wer as jwer

        r = normalize_text(ref, domain)
        h = normalize_text(hyp, domain)
        if not r:
            return 0.0 if not h else 1.0
        return float(jwer(r, h))
    except Exception:
        rt = normalize_text(ref, domain).split()
        ht = normalize_text(hyp, domain).split()
        if not rt:
            return 0.0 if not ht else 1.0
        return 1.0 - (len(set(rt) & set(ht)) / len(set(rt)))


def intent_preserved(ref: str, hyp: str, domain: bool = False) -> bool:
    rt = [t for t in normalize_text(ref, domain).split() if len(t) > 2]
    if not rt:
        return normalize_text(ref, domain) == normalize_text(hyp, domain)
    ht = set(normalize_text(hyp, domain).split())
    hits = sum(1 for t in rt if t in ht)
    return (hits / len(rt)) >= 0.5


def first_span_ok(ref: str, hyp: str, domain: bool = False) -> bool:
    rt = normalize_text(ref, domain).split()
    ht = normalize_text(hyp, domain).split()
    if not rt:
        return True
    return bool(ht) and ht[0] == rt[0]


def term_hits(ref: str, hyp: str, domain: bool = False) -> tuple[int, int]:
    r = normalize_text(ref, domain)
    h = normalize_text(hyp, domain)
    present = [t for t in SAATHI_TERMS if t in r]
    if not present:
        return 0, 0
    hits = sum(1 for t in present if t in h)
    return hits, len(present)


def rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def load_manifest(path: Path | None = None):
    path = path or (CORPUS / "manifest.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return [i for i in data["items"] if i.get("wav")]


def run_candidate(name: str, model_path: str, items: list, language_mode: str = "ne"):
    from faster_whisper import WhisperModel

    print(f"\n=== {name} path={model_path} lang={language_mode} ===")
    t0 = time.perf_counter()
    model = WhisperModel(model_path, device="cpu", compute_type="int8")
    load_s = time.perf_counter() - t0
    print(f"cold load {load_s:.2f}s rss≈{rss_mib():.0f} MiB")

    rows = []
    decode_times = []
    for it in items:
        wav = CORPUS / it["wav"]
        if not wav.exists():
            continue
        # language policy: specialized NE model defaults to ne; mixed/en use auto
        lang = it.get("lang")
        if language_mode == "auto":
            lang_arg = None
        elif language_mode == "ne":
            lang_arg = "ne" if lang in ("ne", "mixed") else ("en" if lang == "en" else "ne")
        else:
            lang_arg = language_mode

        t1 = time.perf_counter()
        segments, info = model.transcribe(
            str(wav), language=lang_arg, beam_size=1, vad_filter=True
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        decode_s = time.perf_counter() - t1
        decode_times.append(decode_s)
        ref = it["text"]
        # RAW metrics
        w = wer(ref, text, domain=False)
        c = cer(ref, text, domain=False)
        intent = intent_preserved(ref, text, domain=False)
        first = first_span_ok(ref, text, domain=False)
        th, tt = term_hits(ref, text, domain=False)
        # NORMALIZED + domain vocab metrics (reporting only; gate uses RAW)
        wn = wer(ref, text, domain=True)
        cn = cer(ref, text, domain=True)
        intent_n = intent_preserved(ref, text, domain=True)
        first_n = first_span_ok(ref, text, domain=True)
        thn, ttn = term_hits(ref, text, domain=True)
        rows.append(
            {
                "id": it["id"],
                "category": it["category"],
                "lang": lang,
                "ref": ref,
                "hyp": text,
                "raw": {
                    "wer": w,
                    "cer": c,
                    "intent_ok": intent,
                    "first_span_ok": first,
                    "term_hits": th,
                    "term_total": tt,
                },
                "normalized_domain": {
                    "wer": wn,
                    "cer": cn,
                    "intent_ok": intent_n,
                    "first_span_ok": first_n,
                    "term_hits": thn,
                    "term_total": ttn,
                },
                "decode_s": decode_s,
                "detected_language": getattr(info, "language", None),
            }
        )
        print(
            f"  {it['id']}: CER={c:.2f} intent={intent} | {text[:90]!r}"
        )

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

    def summarize(group, key="raw"):
        if not group:
            return None
        metrics = [x[key] for x in group]
        intents = [1 if m["intent_ok"] else 0 for m in metrics]
        cers = [m["cer"] for m in metrics]
        wers = [m["wer"] for m in metrics]
        firsts = [1 if m["first_span_ok"] else 0 for m in metrics]
        th = sum(m["term_hits"] for m in metrics)
        tt = sum(m["term_total"] for m in metrics)
        return {
            "n": len(group),
            "mean_wer": sum(wers) / len(wers),
            "mean_cer": sum(cers) / len(cers),
            "intent_rate": sum(intents) / len(intents),
            "first_span_rate": sum(firsts) / len(firsts),
            "term_preservation": (th / tt) if tt else None,
        }

    by_lang = defaultdict(list)
    by_cat = defaultdict(list)
    for r in rows:
        by_lang[r["lang"]].append(r)
        by_cat[r["category"]].append(r)

    ne_rows = [r for r in rows if r["category"] in ("NE_CMD", "MIX") or r["lang"] in ("ne", "mixed")]
    ne_sum = summarize(ne_rows, "raw")
    ne_sum_norm = summarize(ne_rows, "normalized_domain")
    gate = {
        "intent_ok": ne_sum and ne_sum["intent_rate"] >= NEPALI_GATES["intent_preservation_min"],
        "first_span_ok": ne_sum
        and ne_sum["first_span_rate"] >= NEPALI_GATES["first_span_preservation_min"],
        "cer_ok": ne_sum and ne_sum["mean_cer"] <= NEPALI_GATES["cer_max"],
        "term_ok": True
        if not ne_sum or ne_sum["term_preservation"] is None
        else ne_sum["term_preservation"] >= NEPALI_GATES["term_preservation_min"],
    }
    gate["passed"] = all(gate.values())
    # Gate NEVER uses normalized_domain metrics

    out = {
        "candidate": name,
        "model_path": model_path,
        "language_mode": language_mode,
        "cold_load_s": load_s,
        "peak_rss_mib": rss_mib(),
        "latency_decode_s": pct(decode_times),
        "by_language_raw": {k: summarize(v, "raw") for k, v in by_lang.items()},
        "by_language_normalized_domain": {
            k: summarize(v, "normalized_domain") for k, v in by_lang.items()
        },
        "by_category_raw": {k: summarize(v, "raw") for k, v in by_cat.items()},
        "nepali_gate": {
            "criteria": NEPALI_GATES,
            "metrics_raw": ne_sum,
            "metrics_normalized_domain_NOT_USED_FOR_GATE": ne_sum_norm,
            "result": gate,
            "note": "Gate uses RAW metrics only. Normalized reported for analysis.",
        },
        "rows": rows,
    }
    path = RESULTS / f"{name.replace('/', '_').replace(' ', '_')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path}")
    print(f"GATE passed={gate['passed']} raw={ne_sum}")
    return out


def main():
    import os

    items = load_manifest()
    if not items:
        print("No corpus; need tools/voice-stt-bench/corpus")
        return 1

    model_root = Path.home() / ".saathi/stt-models/v-next-2b2"
    # Discover CT2 models
    candidates = []
    for p in sorted(model_root.glob("*-ct2")):
        if (p / "model.bin").exists() or (p / "model.bin").exists():
            candidates.append((p.name, str(p)))
    # Also allow env override
    extra = os.environ.get("STT_SPECIALIZED_MODELS", "")
    for part in extra.split(","):
        part = part.strip()
        if part:
            candidates.append((Path(part).name, part))

    if not candidates:
        print("No CT2 models under", model_root)
        return 2

    results = []
    for name, path in candidates:
        try:
            # primary: language-aware specialized
            results.append(run_candidate(name, path, items, language_mode="ne"))
            # also auto for mixed handling comparison if memory allows
            # skip second pass by default to save RAM — enable via env
            if os.environ.get("STT_ALSO_AUTO") == "1":
                results.append(run_candidate(f"{name}-auto", path, items, language_mode="auto"))
        except Exception as e:
            print(f"FAILED {name}: {e}")
            results.append({"candidate": name, "error": str(e)})

    summary = {
        "mission": "V-NEXT-2B.2",
        "locked_gates": NEPALI_GATES,
        "gate_metric_basis": "RAW only",
        "candidates": [
            {
                "name": r.get("candidate"),
                "error": r.get("error"),
                "nepali_gate_passed": (r.get("nepali_gate") or {}).get("result", {}).get("passed"),
                "gate_detail": (r.get("nepali_gate") or {}).get("result"),
                "metrics_raw": (r.get("nepali_gate") or {}).get("metrics_raw"),
                "by_language_raw": r.get("by_language_raw"),
                "latency": r.get("latency_decode_s"),
                "peak_rss_mib": r.get("peak_rss_mib"),
                "cold_load_s": r.get("cold_load_s"),
            }
            for r in results
        ],
    }
    (RESULTS / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

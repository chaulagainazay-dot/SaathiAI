#!/usr/bin/env python3
"""Generate code-switch + numeric evaluation corpus (TTS). Locked gates already defined."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
CS = CORPUS / "codeswitch"
WAV = CS / "wav"
TXT = CS / "transcripts"

# Code-switch SaathiOS utterances (do not change after results)
CS_UTTERANCES = [
    {"id": "cs_001", "lang": "mixed", "category": "MIX_CS", "text": "आजको portfolio risk explain गर"},
    {"id": "cs_002", "lang": "mixed", "category": "MIX_CS", "text": "मेरो pending approvals show गर"},
    {"id": "cs_003", "lang": "mixed", "category": "MIX_CS", "text": "Trading Guardian को status के छ?"},
    {"id": "cs_004", "lang": "mixed", "category": "MIX_CS", "text": "आजको NAV र drawdown compare गर"},
    {"id": "cs_005", "lang": "mixed", "category": "MIX_CS", "text": "Saathi, current portfolio exposure कति छ?"},
    {"id": "cs_006", "lang": "mixed", "category": "MIX_CS", "text": "यो proposal approve नगर"},
    {"id": "cs_007", "lang": "mixed", "category": "MIX_CS", "text": "Stop, त्यो action cancel गर"},
    {"id": "cs_008", "lang": "mixed", "category": "MIX_CS", "text": "Saathi, system health check गर"},
    {"id": "cs_009", "lang": "mixed", "category": "MIX_CS", "text": "ExecutionGateway healthy छ?"},
    {"id": "cs_010", "lang": "mixed", "category": "MIX_CS", "text": "आजको market मा मेरो biggest risk के हो?"},
    {"id": "cs_011", "lang": "mixed", "category": "MIX_CS", "text": "Portfolio rebalance proposal देखाऊ"},
    {"id": "cs_012", "lang": "mixed", "category": "MIX_CS", "text": "Show my missions र approvals"},
    # English-first switches
    {"id": "cs_013", "lang": "mixed", "category": "MIX_CS", "text": "Open command center र system health देखाऊ"},
    {"id": "cs_014", "lang": "mixed", "category": "MIX_CS", "text": "Cancel that response र फेरि सुन"},
    # Numeric / financial safety
    {"id": "nm_001", "lang": "en", "category": "NUMERIC", "text": "Reduce position by five percent."},
    {"id": "nm_002", "lang": "en", "category": "NUMERIC", "text": "Set stop-loss at fifteen percent."},
    {"id": "nm_003", "lang": "en", "category": "NUMERIC", "text": "Buy five hundred shares."},
    {"id": "nm_004", "lang": "en", "category": "NUMERIC", "text": "NAV is fifty thousand NPR."},
    {"id": "nm_005", "lang": "en", "category": "NUMERIC", "text": "Drawdown is one point five percent."},
    {"id": "nm_006", "lang": "mixed", "category": "NUMERIC", "text": "आजको drawdown five percent छ?"},
    {"id": "nm_007", "lang": "mixed", "category": "NUMERIC", "text": "Position size पाँच सय shares राख"},
    # Proper nouns
    {"id": "pn_001", "lang": "en", "category": "PROPER", "text": "SaathiOS Trading Guardian status."},
    {"id": "pn_002", "lang": "en", "category": "PROPER", "text": "Is ExecutionGateway healthy?"},
    {"id": "pn_003", "lang": "mixed", "category": "PROPER", "text": "Ollama model idle छ कि छैन?"},
]

FINANCE_TERMS = [
    "portfolio", "risk", "nav", "drawdown", "rebalance", "exposure",
    "trading guardian", "executiongateway", "approvals", "missions",
    "saathi", "stop-loss", "percent", "shares",
]

NUMBERS = ["5", "five", "15", "fifteen", "500", "five hundred", "50000", "fifty thousand", "1.5", "one point five"]


def aiff_to_wav16k(aiff: Path, wav: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff), "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(wav)],
        check=True,
        capture_output=True,
    )


def say_en(text: str, wav: Path) -> None:
    aiff = wav.with_suffix(".aiff")
    subprocess.run(["say", "-v", "Samantha", "-o", str(aiff), text], check=True)
    aiff_to_wav16k(aiff, wav)
    aiff.unlink(missing_ok=True)


async def edge_tts_to_wav(text: str, voice: str, wav: Path) -> None:
    import edge_tts

    mp3 = wav.with_suffix(".mp3")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(mp3))
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3), "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(wav)],
        check=True,
        capture_output=True,
    )
    mp3.unlink(missing_ok=True)


async def main() -> int:
    WAV.mkdir(parents=True, exist_ok=True)
    TXT.mkdir(parents=True, exist_ok=True)
    items = []
    for u in CS_UTTERANCES:
        wav = WAV / f"{u['id']}.wav"
        txt = TXT / f"{u['id']}.txt"
        txt.write_text(u["text"] + "\n", encoding="utf-8")
        try:
            if u["lang"] == "en":
                say_en(u["text"], wav)
            else:
                try:
                    await edge_tts_to_wav(u["text"], "ne-NP-SagarNeural", wav)
                except Exception:
                    try:
                        await edge_tts_to_wav(u["text"], "hi-IN-MadhurNeural", wav)
                    except Exception:
                        say_en(u["text"], wav)
            items.append({**u, "wav": str(wav.relative_to(CORPUS)), "source": "tts_local"})
            print("OK", u["id"])
        except Exception as e:
            print("FAIL", u["id"], e, file=sys.stderr)
            items.append({**u, "wav": None, "error": str(e)})

    manifest = {
        "version": "v-next-2b3-codeswitch",
        "note": "Code-switch + numeric corpus. Gates locked before generation.",
        "finance_terms": FINANCE_TERMS,
        "numbers": NUMBERS,
        "count": len(items),
        "items": items,
    }
    (CS / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote", CS / "manifest.json", "n=", len(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

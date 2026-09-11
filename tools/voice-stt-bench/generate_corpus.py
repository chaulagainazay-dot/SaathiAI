#!/usr/bin/env python3
"""Generate local STT evaluation corpus (TTS). Owner live recordings remain separate."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
WAV = CORPUS / "wav"
TXT = CORPUS / "transcripts"

UTTERANCES = [
    # English commands
    {"id": "en_001", "lang": "en", "category": "EN_CMD", "text": "Saathi, show my active missions."},
    {"id": "en_002", "lang": "en", "category": "EN_CMD", "text": "Open the command center."},
    {"id": "en_003", "lang": "en", "category": "EN_CMD", "text": "Stop."},
    {"id": "en_004", "lang": "en", "category": "EN_CMD", "text": "Cancel that response."},
    {"id": "en_005", "lang": "en", "category": "EN_CMD", "text": "Show portfolio risk."},
    {"id": "en_006", "lang": "en", "category": "EN_CMD", "text": "What is Trading Guardian status?"},
    {"id": "en_007", "lang": "en", "category": "EN_CMD", "text": "Is ExecutionGateway healthy?"},
    {"id": "en_008", "lang": "en", "category": "EN_CMD", "text": "Compare today's NAV and drawdown."},
    # Short
    {"id": "sh_001", "lang": "en", "category": "SHORT", "text": "Stop."},
    {"id": "sh_002", "lang": "en", "category": "SHORT", "text": "Cancel."},
    {"id": "sh_003", "lang": "en", "category": "SHORT", "text": "Wait."},
    # Nepali / mixed (Devanagari)
    {"id": "ne_001", "lang": "ne", "category": "NE_CMD", "text": "मेरो आजको portfolio risk देखाऊ।"},
    {"id": "ne_002", "lang": "ne", "category": "NE_CMD", "text": "आजको market exposure कति छ?"},
    {"id": "ne_003", "lang": "ne", "category": "NE_CMD", "text": "मेरो pending approvals के छन्?"},
    {"id": "ne_004", "lang": "ne", "category": "NE_CMD", "text": "Trading Guardian को current status देखाऊ।"},
    {"id": "ne_005", "lang": "ne", "category": "NE_CMD", "text": "आजको NAV र drawdown compare गर।"},
    {"id": "ne_006", "lang": "ne", "category": "NE_CMD", "text": "कमान्ड सेन्टर खोल।"},
    {"id": "mx_001", "lang": "mixed", "category": "MIX", "text": "Saathi, आजको portfolio मा सबैभन्दा ठूलो risk के हो?"},
    {"id": "mx_002", "lang": "mixed", "category": "MIX", "text": "Portfolio rebalance proposal देखाऊ।"},
    {"id": "mx_003", "lang": "mixed", "category": "MIX", "text": "ExecutionGateway healthy छ कि छैन?"},
    {"id": "mx_004", "lang": "mixed", "category": "MIX", "text": "Show my missions र approvals।"},
    {"id": "mx_005", "lang": "mixed", "category": "MIX", "text": "Drawdown कति छ today?"},
    # Long
    {
        "id": "lg_001",
        "lang": "en",
        "category": "LONG",
        "text": "Can you explain the largest risk in my portfolio today and what I should review before any rebalance?",
    },
    {
        "id": "lg_002",
        "lang": "mixed",
        "category": "LONG",
        "text": "Saathi, summarize active missions, pending approvals, and Trading Guardian status in one short brief.",
    },
    # Financial / SaathiOS
    {"id": "fn_001", "lang": "en", "category": "FIN", "text": "Show current NAV and drawdown."},
    {"id": "fn_002", "lang": "en", "category": "FIN", "text": "Portfolio rebalance proposal."},
    {"id": "sa_001", "lang": "en", "category": "SAATHI", "text": "Trading Guardian current status."},
    {"id": "sa_002", "lang": "en", "category": "SAATHI", "text": "ExecutionGateway healthy check."},
    # Backchannel
    {"id": "bc_001", "lang": "ne", "category": "SHORT", "text": "हजुर"},
]


def aiff_to_wav16k(aiff: Path, wav: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(aiff),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            str(wav),
        ],
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
        [
            "ffmpeg",
            "-y",
            "-i",
            str(mp3),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            str(wav),
        ],
        check=True,
        capture_output=True,
    )
    mp3.unlink(missing_ok=True)


def add_noise(src: Path, dst: Path, noise_level: float = 0.08) -> None:
    import array
    import random

    with wave.open(str(src), "rb") as r:
        params = r.getparams()
        frames = r.readframes(r.getnframes())
    samples = array.array("h")
    samples.frombytes(frames)
    amp = int(32767 * noise_level)
    for i in range(len(samples)):
        samples[i] = max(-32767, min(32767, samples[i] + random.randint(-amp, amp)))
    with wave.open(str(dst), "wb") as w:
        w.setparams(params)
        w.writeframes(samples.tobytes())


async def main() -> int:
    WAV.mkdir(parents=True, exist_ok=True)
    TXT.mkdir(parents=True, exist_ok=True)
    items = []
    for u in UTTERANCES:
        wav = WAV / f"{u['id']}.wav"
        txt = TXT / f"{u['id']}.txt"
        txt.write_text(u["text"] + "\n", encoding="utf-8")
        try:
            if u["lang"] == "en":
                say_en(u["text"], wav)
            else:
                # Nepali / mixed: edge-tts Hindi voice as closest available Devanagari path
                voice = "ne-NP-SagarNeural" if u["lang"] == "ne" else "en-US-JennyNeural"
                try:
                    await edge_tts_to_wav(u["text"], voice, wav)
                except Exception:
                    # Fallback: try Hindi neural for Devanagari
                    try:
                        await edge_tts_to_wav(u["text"], "hi-IN-MadhurNeural", wav)
                    except Exception:
                        # Last resort: macOS say English voice reading romanization label
                        say_en(u["text"], wav)
            items.append({**u, "wav": str(wav.relative_to(CORPUS)), "source": "tts_local"})
            print(f"OK {u['id']}")
        except Exception as e:
            print(f"FAIL {u['id']}: {e}", file=sys.stderr)
            items.append({**u, "wav": None, "error": str(e)})

    # Noise variants of two English clips if present
    for src_id, noise_id in [("en_001", "nz_001"), ("en_005", "nz_002")]:
        src = WAV / f"{src_id}.wav"
        if src.exists():
            dst = WAV / f"{noise_id}.wav"
            add_noise(src, dst)
            ref = next(x for x in UTTERANCES if x["id"] == src_id)
            (TXT / f"{noise_id}.txt").write_text(ref["text"] + "\n", encoding="utf-8")
            items.append(
                {
                    "id": noise_id,
                    "lang": "en",
                    "category": "NOISE",
                    "text": ref["text"],
                    "wav": str(dst.relative_to(CORPUS)),
                    "source": "tts_local+noise",
                }
            )
            print(f"OK {noise_id}")

    manifest = {
        "version": "v-next-2b1",
        "note": "Locally generated TTS corpus. Owner live qualification is separate.",
        "count": len(items),
        "items": items,
    }
    (CORPUS / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(items)} items -> {CORPUS / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

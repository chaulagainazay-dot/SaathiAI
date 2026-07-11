"""M12 Voice OS CLI — `python -m saathi.voice_os.cli <cmd>`.

  inspect              provider status + recent sessions (read-only)
  providers            STT/TTS provider health matrix (read-only)
  voices               list available TTS voices (read-only)
  health                same as inspect
  sessions              list sessions (read-only)
  latency <session-id>  latency breakdown for a session (read-only)
  test-stt              REAL adapter test (round-trips synth audio, marks
                        which real path ran: faster_whisper vs deterministic)
  test-tts              REAL adapter test (invokes the real TTS adapter and
                        reports byte count / provider actually used)

Exit codes: 0 ok · 1 provider unavailable · 2 bad command.
Read-only commands never mutate state. Provider test commands are labeled
by exactly which layer they exercised (adapter vs configuration vs real call).
"""
from __future__ import annotations

import json
import sys

from saathi.voice_os.store import default_store
from saathi.voice_os import stt as stt_mod
from saathi.voice_os import tts as tts_mod
from saathi.voice_os.vad import synth_speech

EXIT_OK, EXIT_UNAVAILABLE, EXIT_BAD = 0, 1, 2


def _emit(obj) -> None:
    print(json.dumps(obj, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return EXIT_OK
    cmd, *rest = argv
    st = default_store()

    if cmd in ("inspect", "health"):
        _emit({"stt": stt_mod.provider_status(), "tts": tts_mod.provider_status(),
              "recent_sessions": st.list_sessions(limit=10)})
        return EXIT_OK
    if cmd == "providers":
        _emit({"stt": stt_mod.provider_status(), "tts": tts_mod.provider_status()})
        return EXIT_OK
    if cmd == "voices":
        import shutil, subprocess
        if shutil.which("say"):
            out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True,
                                 timeout=5).stdout
            names = [ln.split()[0] for ln in out.splitlines() if ln.strip()]
            _emit({"voices": names[:40], "source": "say (real)"})
        else:
            _emit({"voices": ["default"], "source": "fallback (say unavailable)"})
        return EXIT_OK
    if cmd == "sessions":
        _emit({"sessions": st.list_sessions(limit=50)})
        return EXIT_OK
    if cmd == "latency" and rest:
        sid = rest[0]
        s = st.get_session(sid)
        if not s:
            _emit({"error": "session not found"})
            return EXIT_BAD
        out = {t["id"]: st.latencies(t["id"]) for t in st.list_turns(sid)}
        _emit({"latency": out})
        return EXIT_OK
    if cmd == "test-stt":
        p = stt_mod.select_provider("faster_whisper")
        audio = synth_speech(0.5)
        result = p.transcribe(audio, sample_rate=16000, language="en")
        _emit({"layer": "real local adapter call" if p.name == "faster_whisper"
              else "deterministic fallback (faster_whisper unavailable)",
              "provider": p.name, "available": p.available(),
              "text": result.text, "duration_ms": result.duration_ms})
        return EXIT_OK if p.available() else EXIT_UNAVAILABLE
    if cmd == "test-tts":
        p = tts_mod.select_provider("say")
        result = p.synthesize("voice OS test", voice="default", rate=1.0)
        _emit({"layer": "real local adapter call" if p.name == "say"
              else "deterministic fallback (say unavailable)",
              "provider": p.name, "available": p.available(),
              "audio_bytes": len(result.audio), "duration_ms": result.duration_ms})
        return EXIT_OK if p.available() else EXIT_UNAVAILABLE

    print(f"unknown command: {cmd}\n{__doc__}")
    return EXIT_BAD


if __name__ == "__main__":
    raise SystemExit(main())

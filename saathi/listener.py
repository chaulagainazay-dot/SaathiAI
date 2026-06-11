"""SaathiAI hands-free terminal mode.

Always-on microphone loop:
  1. Energy-based VAD chunks speech out of the mic stream.
  2. faster-whisper transcribes locally (Nepali + English).
  3. Wake word: utterance must start with "Saathi" (साथी / sathi / sati...)
     — except in conversation mode, where follow-ups need no wake word.
  4. Speaker verification on each utterance gates privileged tools.
  5. Reply is spoken aloud; the mic pauses while Saathi talks (no self-echo).

Run:  python -m saathi.listener
"""
import queue
import re
import sys
import time

import numpy as np
import sounddevice as sd

from . import voice
from .agent import SaathiAgent

SR = 16000
FRAME = 0.03            # 30 ms frames
SILENCE_END = 0.7       # this much silence ends an utterance
MAX_UTTERANCE = 20.0    # hard cap, seconds
MIN_UTTERANCE = 0.4     # ignore blips shorter than this
CALIBRATION_SECS = 1.5
FOLLOWUP_WINDOW = 12.0  # after Saathi replies, listen without wake word

WAKE_WORDS = {"sathi", "saathi", "sati", "sathee", "sarthi", "sathy", "sothi",
              "sadi", "swati", "sotty", "sathiya",
              "साथी", "साथि", "साथीले", "साति"}
WAKE_FUZZY_TARGET = "sathi"
WAKE_FUZZY_MIN = 0.65


def strip_wake_word(text: str) -> str | None:
    """If the utterance starts with the wake word (exact or fuzzy), return the
    rest of the command; otherwise None."""
    import difflib
    cleaned = text.strip()
    parts = cleaned.split(None, 1)
    if not parts:
        return None
    first = parts[0].strip(",.!?;:।").lower()
    rest = parts[1].strip() if len(parts) > 1 else ""
    if first in WAKE_WORDS:
        return rest
    ratio = difflib.SequenceMatcher(None, first, WAKE_FUZZY_TARGET).ratio()
    if ratio >= WAKE_FUZZY_MIN:
        return rest
    return None

C = {"dim": "\033[2m", "cyan": "\033[96m", "green": "\033[92m",
     "yellow": "\033[93m", "red": "\033[91m", "end": "\033[0m"}


def log(msg, color="dim"):
    print(f"{C[color]}{msg}{C['end']}", flush=True)


class Listener:
    def __init__(self, on_state=None):
        self.agent = SaathiAgent()
        self.q: queue.Queue = queue.Queue()
        self.noise_floor = 0.01
        self.last_reply_at = 0.0
        # callback(state) — "listening" | "thinking" | "speaking"; for menu bar UI
        self.on_state = on_state or (lambda s: None)

    # ---- mic stream ----
    def _callback(self, indata, frames, t, status):
        self.q.put(indata[:, 0].copy())

    def _rms(self, frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(frame ** 2)))

    def calibrate(self):
        log(f"calibrating mic noise floor ({CALIBRATION_SECS}s, stay quiet)…")
        frames = []
        end = time.time() + CALIBRATION_SECS
        while time.time() < end:
            try:
                frames.append(self.q.get(timeout=1))
            except queue.Empty:
                break
        if frames:
            calibrated = float(np.median([self._rms(f) for f in frames])) * 3
            # clamp: never above 0.015 so normal speech (~0.03+) always triggers,
            # never below 0.004 so silence doesn't
            self.noise_floor = min(max(calibrated, 0.004), 0.015)
        log(f"noise floor: {self.noise_floor:.4f}")

    def capture_utterance(self) -> np.ndarray | None:
        """Block until one spoken utterance is captured; return float32 mono @16k."""
        buf, started, silence = [], False, 0.0
        start_time = None
        while True:
            try:
                frame = self.q.get(timeout=1)
            except queue.Empty:
                continue
            loud = self._rms(frame) > self.noise_floor
            if not started:
                if loud:
                    started = True
                    start_time = time.time()
                    buf.append(frame)
                continue
            buf.append(frame)
            silence = 0.0 if loud else silence + len(frame) / SR
            dur = time.time() - start_time
            if silence >= SILENCE_END or dur >= MAX_UTTERANCE:
                wav = np.concatenate(buf)
                return wav if len(wav) / SR >= MIN_UTTERANCE else None

    # ---- main loop ----
    def run(self):
        log("loading speech models (first run downloads ~500MB)…", "cyan")
        voice._get_whisper()
        log("SaathiAI is listening. Say “Saathi, …” (Ctrl-C to quit)", "green")

        with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                            blocksize=int(SR * FRAME), callback=self._callback):
            self.calibrate()
            while True:
                wav = self.capture_utterance()
                if wav is None:
                    continue
                # speaker verification runs in parallel with transcription
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=1) as pool:
                    verify_future = pool.submit(voice.verify_array, wav, SR)
                    stt = voice.transcribe_array(wav, SR)
                text = stt["text"].strip()
                if not text:
                    continue

                in_conversation = (time.time() - self.last_reply_at) < FOLLOWUP_WINDOW
                stripped = strip_wake_word(text)
                if stripped is not None:
                    command = stripped or "hello"
                elif in_conversation:
                    command = text
                else:
                    log(f"(ignored, no wake word): {text}")
                    continue

                self.on_state("thinking")
                log(f"🗣  you [{stt['language']}]: {command}", "cyan")

                try:
                    ver = verify_future.result(timeout=10)
                except Exception as e:
                    ver = {"verified": False, "reason": str(e), "similarity": 0}
                badge = ("✅" if ver["verified"]
                         else "🔒" if ver.get("reason") != "no_profile_enrolled"
                         else "⚠️ no profile")
                log(f"   speaker: {badge} (sim={ver.get('similarity')})")

                try:
                    reply = self.agent.respond(command, session_id="terminal",
                                               speaker_verified=ver["verified"])
                except Exception as e:
                    reply = f"Sorry, error: {e}"
                    log(f"agent error: {e}", "red")

                log(f"🤖 saathi: {reply}", "green")
                self.on_state("speaking")
                # pause capture while speaking so Saathi doesn't hear itself
                with self.q.mutex:
                    self.q.queue.clear()
                try:
                    voice.speak(reply, stt["language"])
                except Exception as e:
                    log(f"tts error: {e}", "red")
                with self.q.mutex:
                    self.q.queue.clear()
                self.last_reply_at = time.time()
                self.on_state("listening")
                log(f"(follow-up window open {FOLLOWUP_WINDOW:.0f}s — just talk)")


def main():
    try:
        Listener().run()
    except KeyboardInterrupt:
        print("\nbye! 👋")
        sys.exit(0)


if __name__ == "__main__":
    main()

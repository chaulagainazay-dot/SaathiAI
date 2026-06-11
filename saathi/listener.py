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

WAKE_WORDS = {"baadar", "badar", "bader", "baader", "bahadur", "bandar", "badal",
              "border", "batter", "bother", "brother", "padar", "vadar", "badaar",
              "buddha", "badr", "budder", "powder", "baadal",
              "बादर", "बादल", "बद्दर", "बादार", "बहादुर", "बाँदर"}
WAKE_FUZZY_TARGETS = ("badar", "baadar", "bahadur", "bandar")
WAKE_FUZZY_MIN = 0.55
WAKE_SCAN_TOKENS = 3  # accept the wake word anywhere in the first few words


def _is_wake(token: str) -> bool:
    import difflib
    t = token.strip(",.!?;:।'\"").lower()
    if not t:
        return False
    if t in WAKE_WORDS:
        return True
    best = max(difflib.SequenceMatcher(None, t, tgt).ratio() for tgt in WAKE_FUZZY_TARGETS)
    if best >= WAKE_FUZZY_MIN:
        return True
    # forgiving fallback: short b/v/p-initial word with a 'd' or trailing 'r'
    if (2 <= len(t) <= 8 and t[0] in "bvp"
            and ("d" in t[1:] or t.endswith("r")) and best >= 0.45):
        return True
    return False


def strip_wake_word(text: str) -> str | None:
    """If the wake word appears within the first few words (exact or fuzzy),
    return everything after it as the command; otherwise None."""
    tokens = text.strip().split()
    for i, tok in enumerate(tokens[:WAKE_SCAN_TOKENS]):
        if _is_wake(tok):
            return " ".join(tokens[i + 1:]).strip()
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
        # Silero neural VAD (what Lemon-style apps use) — far better than a
        # loudness threshold at telling speech from noise
        self.vad = None
        try:
            from silero_vad import load_silero_vad
            self.vad = load_silero_vad()
            self._vad_buf = np.zeros(0, dtype=np.float32)
        except Exception:
            pass  # fall back to RMS energy

    def _is_speech(self, frame: np.ndarray) -> bool:
        """Neural VAD if available (512-sample windows), else RMS threshold."""
        if self.vad is None:
            return self._rms(frame) > self.noise_floor
        import torch
        self._vad_buf = np.concatenate([self._vad_buf, frame])
        prob = None
        while len(self._vad_buf) >= 512:
            chunk, self._vad_buf = self._vad_buf[:512], self._vad_buf[512:]
            prob = float(self.vad(torch.from_numpy(chunk), SR).item())
        if prob is None:
            return self._rms(frame) > self.noise_floor
        return prob > 0.5

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
        """Block until one spoken utterance is captured; return float32 mono @16k.

        Keeps a short pre-roll of audio from BEFORE speech is detected so the
        onset of the first word (the wake word) isn't clipped — clipping was
        making Whisper drop 'Baadar'."""
        from collections import deque
        preroll_frames = max(1, int(0.4 * SR / int(SR * FRAME)))  # ~0.4s of pre-roll
        prebuf: deque = deque(maxlen=preroll_frames)
        buf, started, silence = [], False, 0.0
        start_time = None
        while True:
            try:
                frame = self.q.get(timeout=1)
            except queue.Empty:
                continue
            loud = self._is_speech(frame)
            if not started:
                prebuf.append(frame)
                if loud:
                    started = True
                    start_time = time.time()
                    buf.extend(prebuf)  # include audio before the trigger
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
        log("Baadar is listening. Say “Baadar, …” (Ctrl-C to quit)", "green")

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

                # passive Nepali learning: log every Nepali phrase overheard
                # (local only) to grow Saathi's familiarity with how Ajay speaks
                if stt["language"] == "ne":
                    try:
                        from . import nepali
                        nepali.log_heard(text)
                    except Exception:
                        pass

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
                    from . import selfimprove
                    selfimprove.record_verification(ver.get("similarity", 0),
                                                    ver.get("verified", False))
                except Exception:
                    pass

                try:
                    reply = self.agent.respond(command, session_id="terminal",
                                               speaker_verified=ver["verified"])
                except Exception as e:
                    reply = f"Sorry, error: {e}"
                    log(f"agent error: {e}", "red")

                log(f"🤖 baadar: {reply}", "green")
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

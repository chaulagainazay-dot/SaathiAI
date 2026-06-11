"""Push-to-talk mode — hold the Right Option (⌥) key to talk to Baadar.

No always-on listening: Baadar only records while you HOLD the key, then
transcribes and responds when you release. Private, deliberate, no wake word.

The Fn/Globe key is handled specially by macOS and its release often doesn't
reach apps (causing a stuck recorder), so Right Option is used — it sends clean
press/release events. Set PTT_KEYCODE in .env to use a different key.

Uses a Quartz event tap (needs Accessibility permission, already granted to the
SaathiAI python). Designed to run inside the rumps menu-bar run loop.
"""
import os
import threading
import time

import numpy as np
import sounddevice as sd
import Quartz

from . import voice
from .agent import SaathiAgent

SR = 16000
MIN_HOLD_SAMPLES = int(0.3 * SR)
MAX_RECORD_SEC = 30.0            # safety: never record longer than this
OPTION_FLAG = 0x80000           # kCGEventFlagMaskAlternate (either Option key)
PTT_KEYCODE = int(os.getenv("PTT_KEYCODE", "61"))  # 61 = Right Option, 58 = Left

C = {"dim": "\033[2m", "cyan": "\033[96m", "green": "\033[92m", "red": "\033[91m",
     "end": "\033[0m"}


def log(msg, color="dim"):
    print(f"{C[color]}{msg}{C['end']}", flush=True)


class PushToTalk:
    def __init__(self, on_state=None):
        self.agent = SaathiAgent()
        self.on_state = on_state or (lambda s: None)
        self.recording = False
        self.frames: list[np.ndarray] = []
        self.stream = None
        self.busy = False
        self.session = "ptt"

    # ---- mic ----
    def _mic_cb(self, indata, frames, t, status):
        if self.recording:
            self.frames.append(indata[:, 0].copy())

    def start_recording(self):
        if self.recording or self.busy:
            return
        self.frames = []
        self.recording = True
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                     blocksize=int(SR * 0.03), callback=self._mic_cb)
        self.stream.start()
        self.on_state("recording")
        log("🎤 recording… (release ⌥ to send)", "cyan")
        # safety: auto-stop if a release event is ever missed, so it can't stick
        self._rec_started = time.time()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _watchdog(self):
        start = self._rec_started
        while self.recording and self._rec_started == start:
            if time.time() - start > MAX_RECORD_SEC:
                log("⏱ max record reached — sending", "dim")
                self.stop_recording()
                return
            time.sleep(0.2)

    def stop_recording(self):
        if not self.recording:
            return
        self.recording = False
        try:
            self.stream.stop(); self.stream.close()
        except Exception:
            pass
        self.stream = None
        wav = np.concatenate(self.frames) if self.frames else np.zeros(0, np.float32)
        self.frames = []
        if len(wav) < MIN_HOLD_SAMPLES:
            self.on_state("listening")
            return
        threading.Thread(target=self._process, args=(wav,), daemon=True).start()

    # ---- pipeline (no wake word — holding Fn IS the trigger) ----
    def _process(self, wav: np.ndarray):
        self.busy = True
        self.on_state("thinking")
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as pool:
                vf = pool.submit(voice.verify_array, wav, SR)
                stt = voice.transcribe_array(wav, SR)
            text = stt["text"].strip()
            if not text:
                self.on_state("listening"); self.busy = False; return
            try:
                ver = vf.result(timeout=10)
            except Exception:
                ver = {"verified": False, "similarity": 0}
            log(f"🗣  you [{stt['language']}]: {text}", "cyan")
            reply = self.agent.respond(text, self.session,
                                       speaker_verified=ver.get("verified", False))
            log(f"🤖 baadar: {reply}", "green")
            self.on_state("speaking")
            voice.speak(reply, stt["language"])
        except Exception as e:
            log(f"error: {e}", "red")
        finally:
            self.busy = False
            self.on_state("listening")

    # ---- key event tap (Right Option by default) ----
    def _tap_cb(self, proxy, etype, event, refcon):
        try:
            keycode = Quartz.CGEventGetIntegerValueField(
                event, Quartz.kCGKeyboardEventKeycode)
            if keycode != PTT_KEYCODE:
                return event  # only react to the push-to-talk key
            option_down = bool(Quartz.CGEventGetFlags(event) & OPTION_FLAG)
            if option_down and not self.recording:
                self.start_recording()
            elif not option_down and self.recording:
                self.stop_recording()
        except Exception:
            pass
        return event

    def install_tap(self):
        """Attach the Fn-key tap to the current run loop (call from the rumps app)."""
        mask = Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly, mask, self._tap_cb, None)
        if not tap:
            raise RuntimeError("Could not create event tap — check Accessibility "
                               "permission for the SaathiAI python.")
        src = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), src,
                                  Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        self._tap = tap
        self.on_state("listening")
        log("Baadar push-to-talk ready. HOLD the Right Option (⌥) key to talk.", "green")

    def run_standalone(self):
        """Run with its own run loop (for terminal use without the menu bar)."""
        self.install_tap()
        Quartz.CFRunLoopRun()


def main():
    PushToTalk().run_standalone()


if __name__ == "__main__":
    main()

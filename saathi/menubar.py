"""SaathiAI menu bar app — a small Siri-like icon that shows what Saathi is doing.

  ●  purple  : listening (always-on, hands-free)
  ◐  rainbow : thinking
  ●  green   : speaking
  ○  grey    : paused

Run: python -m saathi.menubar   (replaces the plain terminal listener)
"""
import threading

import rumps

ICONS = {"listening": "🟣", "thinking": "🌀", "speaking": "🟢", "paused": "⚪️"}


class SaathiMenuBar(rumps.App):
    def __init__(self):
        super().__init__(ICONS["paused"], quit_button=None)
        self.menu = ["Pause / Resume", "Open Saathi App", None, "Quit Saathi"]
        self.listener = None
        self.paused = False
        self._start_listener()

    def _set_state(self, state: str):
        if not self.paused:
            self.title = ICONS.get(state, "🟣")

    def _start_listener(self):
        from .listener import Listener
        self.listener = Listener(on_state=self._set_state)
        t = threading.Thread(target=self._run_listener, daemon=True)
        t.start()

    def _run_listener(self):
        self.title = ICONS["listening"]
        try:
            self.listener.run()
        except Exception as e:
            rumps.notification("SaathiAI", "Listener stopped", str(e))
            self.title = ICONS["paused"]

    @rumps.clicked("Pause / Resume")
    def toggle(self, _):
        # soft pause: raise the noise floor so nothing triggers
        if not self.listener:
            return
        self.paused = not self.paused
        if self.paused:
            self._saved_floor = self.listener.noise_floor
            self.listener.noise_floor = 99.0
            self.title = ICONS["paused"]
        else:
            self.listener.noise_floor = getattr(self, "_saved_floor", 0.015)
            self.title = ICONS["listening"]

    @rumps.clicked("Open Saathi App")
    def open_app(self, _):
        import webbrowser
        webbrowser.open("http://localhost:8765")

    @rumps.clicked("Quit Saathi")
    def quit_app(self, _):
        rumps.quit_application()


def main():
    SaathiMenuBar().run()


if __name__ == "__main__":
    main()

"""Baadar menu bar app — push-to-talk.

  🎙️  idle (hold ⌥ to talk)   🔴 recording   🌀 thinking   🟢 speaking

HOLD the Right Option (⌥) key, speak, release. No always-on listening.
Run: python -m saathi.menubar
"""
import threading

import rumps

ICONS = {"listening": "🎙️", "recording": "🔴", "thinking": "🌀",
         "speaking": "🟢", "paused": "⚪️"}


class SaathiMenuBar(rumps.App):
    def __init__(self):
        super().__init__(ICONS["paused"], quit_button=None)
        self.menu = ["Hold Right Option (⌥) to talk", None,
                     "Open Baadar App", "Quit Baadar"]
        self.ptt = None
        self._start_ptt()

    def _set_state(self, state: str):
        self.title = ICONS.get(state, "🌐")

    def _start_ptt(self):
        from .pushtotalk import PushToTalk
        self.ptt = PushToTalk(on_state=self._set_state)
        # the event tap must live on the main run loop, which rumps drives
        try:
            self.ptt.install_tap()
        except Exception as e:
            rumps.notification("Baadar", "Push-to-talk failed to start", str(e))
            self.title = ICONS["paused"]

    @rumps.clicked("Open Baadar App")
    def open_app(self, _):
        import webbrowser
        webbrowser.open("http://localhost:8765")

    @rumps.clicked("Quit Baadar")
    def quit_app(self, _):
        rumps.quit_application()


def main():
    SaathiMenuBar().run()


if __name__ == "__main__":
    main()

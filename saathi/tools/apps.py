"""Built-in app shortcuts that work by voice (WhatsApp, Messages, etc.)."""
from . import mac_control
from .. import vision


def check_messages(app: str = "WhatsApp") -> dict:
    """Open the messaging app and read out who has unread messages."""
    return vision.ask_screen(
        f"Who has sent me unread/new messages in {app}? List the names and a few "
        f"words of each latest message. If nothing is unread, say so.",
        window_app=app)


def look_at_screen(question: str) -> dict:
    """Answer any question about what's currently on screen."""
    return vision.ask_screen(question)


def open_app(app_name: str) -> dict:
    return mac_control.open_app(app_name)


def close_app(app_name: str) -> dict:
    return mac_control.close_app(app_name)

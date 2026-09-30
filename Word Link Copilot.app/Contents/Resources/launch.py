"""Desktop entry point with one-time, standard macOS capture consent onboarding."""

from pathlib import Path
from datetime import datetime, timezone
import tkinter as tk

from wordlink.capture.macos import request_screen_recording, screen_recording_allowed
from wordlink.ui.app import create_app


def main() -> None:
    root = tk.Tk()
    app = create_app(root)
    marker = Path.home() / "Library/Application Support/WordLinkCopilot/.screen-recording-requested"
    status_log = Path.home() / "Library/Logs/WordLinkCopilot/permission-status.log"

    def record(event: str, value: bool) -> None:
        with status_log.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(timezone.utc).isoformat()} {event}={value}\n")

    def offer_capture_permission() -> None:
        allowed = screen_recording_allowed()
        record("preflight_before", allowed)
        if allowed:
            return
        app.show_capture_help()
        if marker.exists():
            return
        marker.touch(mode=0o600)
        try:
            record("request_return", request_screen_recording())
        finally:
            record("preflight_after", screen_recording_allowed())
            app._refresh_permission_status()

    root.after(750, offer_capture_permission)
    root.mainloop()


if __name__ == "__main__":
    main()

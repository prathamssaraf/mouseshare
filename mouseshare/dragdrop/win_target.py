"""
Drag-and-drop target — Windows side.

When a file is received over the network (triggered by a mac-side drag), we:
  1. Save it to the receive folder (FileReceiver already does this).
  2. Show a Windows toast notification: "File received: photo.jpg — click to open".
  3. Optionally open the file's parent folder in Explorer.

True COM IDropTarget injection into the Windows shell is extremely complex and
fragile (requires shell process elevation or undocumented APIs).  Even commercial
tools like ShareMouse use the "save to folder + notify" approach rather than
true desktop drop simulation.  We follow the same pragmatic approach.

Requires: pywin32 (Windows only)
This module is imported only on Windows; the import is guarded in the caller.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def notify_file_received(file_path: Path) -> None:
    """
    Show a native Windows toast notification when a file is received.
    Falls back to a simple message box if toast is unavailable.
    """
    if sys.platform != "win32":
        return

    title   = "MouseShare — File Received"
    message = f"{file_path.name}\nSaved to {file_path.parent}"

    try:
        _toast_windows(title, message, str(file_path))
    except Exception:
        try:
            _msgbox_fallback(title, message)
        except Exception as exc:
            log.warning("Could not show notification: %s", exc)


def open_in_explorer(path: Path) -> None:
    """Open the folder containing the received file and select it."""
    if sys.platform != "win32":
        return
    try:
        subprocess.Popen(["explorer", "/select,", str(path)])
    except Exception as exc:
        log.debug("Explorer open failed: %s", exc)


# ── Notification backends ─────────────────────────────────────────────────────

def _toast_windows(title: str, message: str, file_path: str) -> None:
    """
    Use Windows 10+ toast notifications via win10toast or winotify.
    We try both libraries gracefully.
    """
    try:
        # winotify is the most reliable on Windows 10
        from winotify import Notification, audio
        toast = Notification(
            app_id="MouseShare",
            title=title,
            msg=message,
            duration="short",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.add_actions(label="Open Folder", launch=f"explorer /select,\"{file_path}\"")
        toast.show()
        return
    except ImportError:
        pass

    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=5, threaded=True)
        return
    except ImportError:
        pass

    raise RuntimeError("No toast notification library available")


def _msgbox_fallback(title: str, message: str) -> None:
    import ctypes
    ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)  # MB_ICONINFORMATION

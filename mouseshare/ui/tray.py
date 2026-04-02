"""
System tray icon — provides the primary user-facing control surface.

Menu structure:
  MouseShare  ●  Connected / ✕  Disconnected
  ─────────────────────────────────────────
  Send File...
  ─────────────────────────────────────────
  Settings...
  ─────────────────────────────────────────
  Quit

Uses pystray which works on both macOS and Windows.
The icon image is created programmatically if no asset file is found.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw

log = logging.getLogger(__name__)


def _make_icon_image(connected: bool = False) -> Image.Image:
    """Generate a simple coloured circle as the tray icon."""
    size   = 64
    img    = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(img)
    colour = (0, 180, 80) if connected else (180, 50, 50)   # green / red
    draw.ellipse([4, 4, size - 4, size - 4], fill=colour)
    return img


def _load_icon_image(connected: bool) -> Image.Image:
    assets_dir = Path(__file__).parent.parent.parent / "assets"
    icon_file  = assets_dir / "icon.png"
    if icon_file.exists():
        return Image.open(icon_file).convert("RGBA")
    return _make_icon_image(connected)


class TrayIcon:
    """
    Wraps pystray.Icon and exposes simple methods to update status and
    trigger callbacks.

    All pystray callbacks run on pystray's own thread; we bridge back to
    the asyncio event loop using run_coroutine_threadsafe where needed.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_send_file: Callable,
        on_open_settings: Callable,
        on_quit: Callable,
    ) -> None:
        self._loop             = loop
        self._on_send_file     = on_send_file
        self._on_open_settings = on_open_settings
        self._on_quit          = on_quit
        self._icon: Optional[pystray.Icon] = None
        self._connected        = False

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Run the tray icon (blocks the calling thread — call from a daemon thread)."""
        self._icon = pystray.Icon(
            name="MouseShare",
            icon=_load_icon_image(False),
            title="MouseShare — Disconnected",
            menu=self._build_menu(),
        )
        self._icon.run()

    def start_detached(self) -> threading.Thread:
        """Start the tray icon in its own daemon thread."""
        t = threading.Thread(target=self.start, daemon=True, name="ms-tray")
        t.start()
        return t

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    def set_connected(self, connected: bool, peer: str = "") -> None:
        self._connected = connected
        if self._icon:
            label = f"MouseShare — Connected ({peer})" if connected else "MouseShare — Disconnected"
            self._icon.title = label
            self._icon.icon  = _load_icon_image(connected)
            self._icon.menu  = self._build_menu()
            try:
                self._icon.update_menu()
            except Exception:
                pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_menu(self) -> pystray.Menu:
        status_label = "● Connected" if self._connected else "✕  Disconnected"
        return pystray.Menu(
            pystray.MenuItem(status_label, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Send File...", self._handle_send_file),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings...", self._handle_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._handle_quit),
        )

    def _handle_send_file(self, icon, item) -> None:
        threading.Thread(target=self._on_send_file, daemon=True).start()

    def _handle_settings(self, icon, item) -> None:
        threading.Thread(target=self._on_open_settings, daemon=True).start()

    def _handle_quit(self, icon, item) -> None:
        self._on_quit()

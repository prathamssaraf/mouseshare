"""
Screen geometry helpers — resolution, edge detection, coordinate normalisation.

All mouse coordinates sent over the wire are normalised to 0.0–1.0 so they
map correctly when the two machines have different screen resolutions.
"""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ScreenSize:
    width: int
    height: int


_cached_size: Optional[ScreenSize] = None


def get_screen_size() -> tuple[int, int]:
    """Return (width, height) in pixels for the primary display."""
    global _cached_size
    if _cached_size is not None:
        return _cached_size.width, _cached_size.height

    if sys.platform == "darwin":
        _cached_size = _get_size_mac()
    elif sys.platform == "win32":
        _cached_size = _get_size_windows()
    else:
        _cached_size = _get_size_tkinter()

    return _cached_size.width, _cached_size.height


def _get_size_mac() -> ScreenSize:
    # AppKit NSScreen — stable, thread-safe on macOS
    try:
        from AppKit import NSScreen
        screen = NSScreen.mainScreen()
        if screen is not None:
            frame = screen.frame()
            return ScreenSize(width=int(frame.size.width), height=int(frame.size.height))
    except Exception:
        pass
    # Quartz CGDisplay fallback
    try:
        from Quartz import CGDisplayPixelsWide, CGDisplayPixelsHigh, CGMainDisplayID
        display = CGMainDisplayID()
        return ScreenSize(
            width=CGDisplayPixelsWide(display),
            height=CGDisplayPixelsHigh(display),
        )
    except Exception:
        pass
    return _get_size_tkinter()


def _get_size_windows() -> ScreenSize:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        # Use GetSystemMetrics with SM_CXVIRTUALSCREEN for multi-monitor awareness
        w = user32.GetSystemMetrics(0)   # SM_CXSCREEN (primary)
        h = user32.GetSystemMetrics(1)   # SM_CYSCREEN (primary)
        return ScreenSize(width=w, height=h)
    except Exception:
        return _get_size_tkinter()


def _get_size_tkinter() -> ScreenSize:
    root = tk.Tk()
    root.withdraw()
    w = root.winfo_screenwidth()
    h = root.winfo_screenheight()
    root.destroy()
    return ScreenSize(width=w, height=h)


# ── Coordinate normalisation ──────────────────────────────────────────────────

def normalise(x: int, y: int) -> tuple[float, float]:
    """Convert absolute pixel coordinates to normalised 0.0–1.0 values."""
    w, h = get_screen_size()
    return x / w, y / h


def denormalise(nx: float, ny: float) -> tuple[int, int]:
    """Convert normalised 0.0–1.0 values to absolute pixel coordinates."""
    w, h = get_screen_size()
    return int(nx * w), int(ny * h)


# ── Edge detection ────────────────────────────────────────────────────────────

from mouseshare.constants import (
    DIR_BOTTOM,
    DIR_LEFT,
    DIR_RIGHT,
    DIR_TOP,
    EDGE_THRESHOLD,
)


def detect_edge(x: int, y: int) -> Optional[int]:
    """
    Return a DIR_* constant if (x, y) is within EDGE_THRESHOLD pixels of a
    screen edge, otherwise return None.
    """
    w, h = get_screen_size()
    if x <= EDGE_THRESHOLD:
        return DIR_LEFT
    if x >= w - 1 - EDGE_THRESHOLD:
        return DIR_RIGHT
    if y <= EDGE_THRESHOLD:
        return DIR_TOP
    if y >= h - 1 - EDGE_THRESHOLD:
        return DIR_BOTTOM
    return None


def opposite_edge_position(direction: int, peer_width: int, peer_height: int) -> tuple[int, int]:
    """
    When focus switches to the peer screen via *direction*, return the pixel
    position where the cursor should appear on the peer screen.
    """
    if direction == DIR_RIGHT:
        return 1, peer_height // 2
    if direction == DIR_LEFT:
        return peer_width - 2, peer_height // 2
    if direction == DIR_BOTTOM:
        return peer_width // 2, 1
    if direction == DIR_TOP:
        return peer_width // 2, peer_height - 2
    return peer_width // 2, peer_height // 2

"""
Input injection — runs on the CLIENT (machine receiving input from the server).

Translates decoded packet payloads back into real OS input events using pynput.
Mouse coordinates arrive normalised (0.0–1.0) and are scaled to the local
screen resolution before injection.

Cross-platform:
  macOS  — pynput uses CGEventPost (requires Accessibility permission)
  Windows — pynput uses SendInput (no special permission needed)
"""

from __future__ import annotations

import logging
import sys

from pynput import keyboard as kb
from pynput import mouse as ms

from mouseshare.constants import BTN_LEFT, BTN_MIDDLE, BTN_RIGHT
from mouseshare.input.screen import denormalise, get_screen_size

log = logging.getLogger(__name__)

_mouse_ctrl = ms.Controller()
_kb_ctrl    = kb.Controller()


def _const_to_button(btn: int) -> ms.Button:
    if btn == BTN_RIGHT:
        return ms.Button.right
    if btn == BTN_MIDDLE:
        return ms.Button.middle
    return ms.Button.left


def _int_to_key(code: int):
    """Convert a keycode integer back to a pynput Key or KeyCode."""
    # Check pynput special keys first
    for special in kb.Key:
        try:
            if special.value.vk == code:
                return special
        except Exception:
            pass
    # Fall back to a KeyCode with the vk value
    return kb.KeyCode.from_vk(code)


# ── Injection functions (called from asyncio handlers) ────────────────────────

def inject_mouse_move(nx: float, ny: float) -> None:
    """Move mouse to normalised position (0.0–1.0) on this screen."""
    x, y = denormalise(nx, ny)
    try:
        _mouse_ctrl.position = (x, y)
    except Exception as exc:
        log.debug("Mouse move failed: %s", exc)


def inject_mouse_click(button: int, pressed: bool) -> None:
    btn = _const_to_button(button)
    try:
        if pressed:
            _mouse_ctrl.press(btn)
        else:
            _mouse_ctrl.release(btn)
    except Exception as exc:
        log.debug("Mouse click failed: %s", exc)


def inject_mouse_scroll(dx: int, dy: int) -> None:
    try:
        _mouse_ctrl.scroll(dx, dy)
    except Exception as exc:
        log.debug("Scroll failed: %s", exc)


def inject_key(keycode: int, pressed: bool) -> None:
    key = _int_to_key(keycode)
    try:
        if pressed:
            _kb_ctrl.press(key)
        else:
            _kb_ctrl.release(key)
    except Exception as exc:
        log.debug("Key event failed: %s", exc)


def move_cursor_to_entry_position(direction: int) -> None:
    """
    Place cursor at the correct edge of this screen when focus arrives
    from the server (opposite edge from where the switch happened).
    """
    from mouseshare.constants import DIR_BOTTOM, DIR_LEFT, DIR_RIGHT, DIR_TOP
    from mouseshare.input.screen import opposite_edge_position

    w, h = get_screen_size()
    x, y = opposite_edge_position(direction, w, h)
    try:
        _mouse_ctrl.position = (x, y)
    except Exception as exc:
        log.debug("Cursor placement failed: %s", exc)

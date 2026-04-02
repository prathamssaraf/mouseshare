"""
Global input capture — runs on the SERVER (machine with the physical mouse/keyboard).

Uses pynput for cross-platform global event hooks.

IMPORTANT macOS note:
  pynput on macOS crashes if both mouse and keyboard Listeners are started in
  the same thread.  We start each in its own daemon thread.  This is the
  documented workaround.

The capture layer calls an async callback via asyncio.run_coroutine_threadsafe
so that the asyncio event loop on the main thread receives events without
blocking the pynput listener threads.

Forwarding behaviour:
  When the cursor crosses the trigger edge, _forwarding is set True.
  - The server cursor is pinned at the edge so it does not wander on the
    server screen while the remote cursor is being controlled.
  - All mouse/keyboard events are encoded and dispatched to the client.
  - On macOS, pynput mouse events are suppressed (return False from callback)
    so the local OS does not also act on them.
  - When set_forwarding(False) is called (client sends SWITCH back), the
    server cursor is moved to the centre of its screen.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Awaitable, Callable, Optional

from pynput import keyboard, mouse

from mouseshare.constants import (
    BTN_LEFT,
    BTN_MIDDLE,
    BTN_RIGHT,
    DIR_LEFT,
    DIR_RIGHT,
    DIR_TOP,
    DIR_BOTTOM,
)
from mouseshare.input.screen import detect_edge, get_screen_size, normalise

log = logging.getLogger(__name__)

AsyncCallback = Callable[[bytes], Awaitable[None]]

_mouse_ctrl = mouse.Controller()


def _pynput_button_to_const(btn: mouse.Button) -> int:
    if btn == mouse.Button.left:
        return BTN_LEFT
    if btn == mouse.Button.right:
        return BTN_RIGHT
    return BTN_MIDDLE


def _key_to_int(key) -> int:
    try:
        return key.vk if hasattr(key, "vk") and key.vk else ord(key.char)
    except (AttributeError, TypeError):
        pass
    try:
        return key.value.vk
    except Exception:
        return 0


def _pin_cursor_at_edge(direction: int) -> None:
    """Keep the server cursor just inside the trigger edge so it can't wander."""
    w, h = get_screen_size()
    cx, cy = _mouse_ctrl.position
    if direction == DIR_RIGHT:
        _mouse_ctrl.position = (w - 2, cy)
    elif direction == DIR_LEFT:
        _mouse_ctrl.position = (1, cy)
    elif direction == DIR_TOP:
        _mouse_ctrl.position = (cx, 1)
    elif direction == DIR_BOTTOM:
        _mouse_ctrl.position = (cx, h - 2)


def _move_cursor_to_centre() -> None:
    w, h = get_screen_size()
    _mouse_ctrl.position = (w // 2, h // 2)


class InputCapture:
    """
    Captures global mouse and keyboard events and forwards encoded packets
    to the provided async send callback.

    Usage:
        capture = InputCapture(loop, send_fn, on_edge_fn)
        capture.start()
        ...
        capture.stop()
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        send_packet: AsyncCallback,
        on_edge: Callable[[int], None],
        edge_direction: int = DIR_RIGHT,
    ) -> None:
        self._loop           = loop
        self._send_packet    = send_packet
        self._on_edge        = on_edge
        self._edge_direction = edge_direction

        self._forwarding      = False
        self._edge_pos: tuple[int, int] = (0, 0)
        self._last_move_sent  = 0.0   # monotonic timestamp of last forwarded move

        self._mouse_listener: Optional[mouse.Listener] = None
        self._kb_listener:    Optional[keyboard.Listener] = None
        self._mouse_thread:   Optional[threading.Thread] = None
        self._kb_thread:      Optional[threading.Thread] = None

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start both listeners in separate daemon threads."""
        # Mouse listener: suppress=False so the OS still processes events and
        # the cursor can actually move.  We pin the cursor programmatically
        # during forwarding — mouse.Controller().position uses
        # CGWarpMouseCursorPosition which does NOT generate a new move event,
        # so there is no feedback loop.
        self._mouse_listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._kb_listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )

        # Each listener gets its own daemon thread (required on macOS)
        self._mouse_thread = threading.Thread(
            target=self._mouse_listener.start, daemon=True, name="ms-mouse-capture"
        )
        self._kb_thread = threading.Thread(
            target=self._kb_listener.start, daemon=True, name="ms-keyboard-capture"
        )
        self._mouse_thread.start()
        self._kb_thread.start()
        log.debug("Input capture started")

    def stop(self) -> None:
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._kb_listener:
            self._kb_listener.stop()
        log.debug("Input capture stopped")

    def set_forwarding(self, enabled: bool) -> None:
        """Enable or disable forwarding. When disabling, move cursor to centre."""
        was_forwarding = self._forwarding
        self._forwarding = enabled
        if was_forwarding and not enabled:
            _move_cursor_to_centre()
        log.debug("Input forwarding: %s", "ON" if enabled else "OFF")

    def set_edge_direction(self, direction: int) -> None:
        self._edge_direction = direction

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _dispatch(self, frame: bytes) -> None:
        asyncio.run_coroutine_threadsafe(self._send_packet(frame), self._loop)

    # ── Mouse callbacks ───────────────────────────────────────────────────────

    def _on_move(self, x: int, y: int):
        from mouseshare.network.protocol import encode_mouse_move

        if not self._forwarding:
            edge = detect_edge(x, y)
            if edge == self._edge_direction:
                self._forwarding = True
                self._edge_pos   = (x, y)
                self._on_edge(edge)
            return

        # Pin cursor at edge on every raw event so it can't drift.
        # mouse.Controller().position calls CGWarpMouseCursorPosition which
        # moves the cursor without posting a new mouse event — no feedback loop.
        _pin_cursor_at_edge(self._edge_direction)

        # Throttle network sends to ~60 fps.  pynput can fire 200-1000 events/s
        # on a high-polling mouse; without throttling the asyncio send queue
        # backs up and causes visible lag on the client.
        now = time.monotonic()
        if now - self._last_move_sent < 0.0167:   # 1/60 s ≈ 16.7 ms
            return
        self._last_move_sent = now

        nx, ny = normalise(x, y)
        self._dispatch(encode_mouse_move(nx, ny))

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool):
        from mouseshare.network.protocol import encode_mouse_click

        if self._forwarding:
            self._dispatch(encode_mouse_click(_pynput_button_to_const(button), pressed))

    def _on_scroll(self, x: int, y: int, dx: int, dy: int):
        from mouseshare.network.protocol import encode_mouse_scroll

        if self._forwarding:
            self._dispatch(encode_mouse_scroll(dx, dy))

    # ── Keyboard callbacks ────────────────────────────────────────────────────

    def _on_press(self, key) -> None:
        from mouseshare.network.protocol import encode_key_event

        if self._forwarding:
            code = _key_to_int(key)
            if code:
                self._dispatch(encode_key_event(code, pressed=True))

    def _on_release(self, key) -> None:
        from mouseshare.network.protocol import encode_key_event

        if self._forwarding:
            code = _key_to_int(key)
            if code:
                self._dispatch(encode_key_event(code, pressed=False))

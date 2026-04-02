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
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
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
from mouseshare.input.screen import detect_edge, normalise

log = logging.getLogger(__name__)

# Type for the async callbacks we hand up to the session layer
AsyncCallback = Callable[[bytes], Awaitable[None]]


def _pynput_button_to_const(btn: mouse.Button) -> int:
    if btn == mouse.Button.left:
        return BTN_LEFT
    if btn == mouse.Button.right:
        return BTN_RIGHT
    return BTN_MIDDLE


def _key_to_int(key) -> int:
    """Map a pynput Key or KeyCode to a stable integer keycode."""
    try:
        # Regular character key
        return key.vk if hasattr(key, "vk") and key.vk else ord(key.char)
    except (AttributeError, TypeError):
        pass
    try:
        # Special key (e.g. Key.shift)
        return key.value.vk
    except Exception:
        return 0


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
        """
        Args:
            loop:           The running asyncio event loop.
            send_packet:    Coroutine called with an encoded packet bytes when
                            an input event should be forwarded to the client.
            on_edge:        Synchronous callback called with a DIR_* constant
                            when the mouse crosses the configured screen edge.
            edge_direction: Which screen edge leads to the other machine.
        """
        self._loop = loop
        self._send_packet = send_packet
        self._on_edge = on_edge
        self._edge_direction = edge_direction

        self._forwarding = False    # True when mouse/keyboard should be sent to client
        self._mouse_listener: Optional[mouse.Listener] = None
        self._kb_listener: Optional[keyboard.Listener] = None
        self._mouse_thread: Optional[threading.Thread] = None
        self._kb_thread: Optional[threading.Thread] = None

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start both listeners in separate daemon threads."""
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
        """Enable or disable forwarding of events to the remote client."""
        self._forwarding = enabled
        log.debug("Input forwarding: %s", "ON" if enabled else "OFF")

    def set_edge_direction(self, direction: int) -> None:
        self._edge_direction = direction

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _dispatch(self, frame: bytes) -> None:
        """Thread-safe: schedule send on the asyncio event loop."""
        asyncio.run_coroutine_threadsafe(self._send_packet(frame), self._loop)

    # ── Mouse callbacks ───────────────────────────────────────────────────────

    def _on_move(self, x: int, y: int) -> None:
        from mouseshare.network.protocol import encode_mouse_move

        edge = detect_edge(x, y)
        if edge == self._edge_direction and not self._forwarding:
            # Mouse hit the configured edge — switch to remote
            self._forwarding = True
            self._on_edge(edge)
            return

        if self._forwarding:
            nx, ny = normalise(x, y)
            self._dispatch(encode_mouse_move(nx, ny))

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        from mouseshare.network.protocol import encode_mouse_click

        if self._forwarding:
            self._dispatch(encode_mouse_click(_pynput_button_to_const(button), pressed))

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
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

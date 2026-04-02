"""
TCP client — runs on the machine receiving input from the server.

Maintains a persistent connection with exponential-backoff reconnection.
All channels (input, clipboard, file transfer) share the same connection.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine

from mouseshare.config import Config
from mouseshare.constants import (
    KEEPALIVE_INTERVAL,
    MSG_CLIP_IMAGE,
    MSG_CLIP_TEXT,
    MSG_DISCONNECT,
    MSG_DRAG_START,
    MSG_FILE_CHUNK,
    MSG_FILE_END,
    MSG_FILE_NACK,
    MSG_FILE_START,
    MSG_HANDSHAKE,
    MSG_KEEPALIVE,
    MSG_KEY_EVENT,
    MSG_MOUSE_CLICK,
    MSG_MOUSE_MOVE,
    MSG_MOUSE_SCROLL,
    MSG_SCREEN_INFO,
    MSG_SWITCH,
    RECONNECT_BASE,
    RECONNECT_MAX,
)
from mouseshare.network.protocol import (
    decode_handshake,
    decode_screen_info,
    encode_handshake,
    encode_keepalive,
    encode_screen_info,
    read_packet,
)
from mouseshare.network.tls import client_ssl_context

log = logging.getLogger(__name__)

PacketHandler = Callable[[int, bytes], Coroutine]


class MouseShareClient:
    """
    Connects to a MouseShareServer, reconnects automatically on drop.
    Dispatches incoming packets to registered handlers.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._handlers: dict[int, PacketHandler] = {}
        self._stop_event = asyncio.Event()
        self._connected = asyncio.Event()
        self._peer_screen: tuple[int, int] | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def register(self, msg_type: int, fn: PacketHandler) -> None:
        self._handlers[msg_type] = fn

    async def send(self, frame: bytes) -> None:
        if self._writer is None:
            return
        async with self._lock:
            try:
                self._writer.write(frame)
                await self._writer.drain()
            except (ConnectionResetError, BrokenPipeError, OSError) as exc:
                log.warning("Send failed: %s", exc)
                self._writer = None
                self._connected.clear()

    async def wait_for_connection(self) -> None:
        await self._connected.wait()

    @property
    def is_connected(self) -> bool:
        return self._writer is not None

    @property
    def peer_screen(self) -> tuple[int, int] | None:
        return self._peer_screen

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Connect and reconnect until stop() is called."""
        delay = RECONNECT_BASE
        while not self._stop_event.is_set():
            try:
                await self._connect_and_run()
                delay = RECONNECT_BASE  # reset on clean disconnect
            except (ConnectionRefusedError, OSError, asyncio.TimeoutError) as exc:
                log.warning("Connection failed (%s) — retrying in %.1fs", exc, delay)
                self._connected.clear()
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=delay
                    )
                except asyncio.TimeoutError:
                    pass
                delay = min(delay * 2, RECONNECT_MAX)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass

    # ── Connection handling ───────────────────────────────────────────────────

    async def _connect_and_run(self) -> None:
        cfg = self.config
        ssl_ctx = client_ssl_context() if cfg.tls_enabled else None

        log.info("Connecting to %s:%s (TLS=%s)", cfg.host, cfg.port, cfg.tls_enabled)
        reader, writer = await asyncio.open_connection(
            host=cfg.host, port=cfg.port, ssl=ssl_ctx
        )
        self._writer = writer
        log.info("Connected to server")

        # Exchange handshake
        writer.write(encode_handshake())
        await writer.drain()

        # Send our screen info
        from mouseshare.input.screen import get_screen_size
        w, h = get_screen_size()
        await self.send(encode_screen_info(w, h))

        self._connected.set()

        try:
            await asyncio.gather(
                self._read_loop(reader),
                self._keepalive_loop(),
            )
        finally:
            self._writer = None
            self._connected.clear()
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        while True:
            msg_type, payload = await read_packet(reader)

            if msg_type == MSG_DISCONNECT:
                log.info("Server sent graceful disconnect")
                break

            if msg_type == MSG_KEEPALIVE:
                continue

            if msg_type == MSG_SCREEN_INFO:
                w, h = decode_screen_info(payload)
                self._peer_screen = (w, h)
                log.debug("Server screen size: %dx%d", w, h)
                continue

            if msg_type == MSG_HANDSHAKE:
                info = decode_handshake(payload)
                log.debug("Server handshake: %s", info)
                continue

            handler = self._handlers.get(msg_type)
            if handler:
                await handler(msg_type, payload)
            else:
                log.debug("No handler for msg_type=0x%02X (len=%d)", msg_type, len(payload))

    async def _keepalive_loop(self) -> None:
        while self._writer is not None:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
            await self.send(encode_keepalive())

"""
TCP server — runs on the machine with the physical mouse/keyboard.

Accepts one client at a time.  Multiplexes all channels (input events,
clipboard, file transfer) over a single TLS-wrapped TCP connection.
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
)
from mouseshare.network.protocol import (
    decode_handshake,
    decode_mouse_click,
    decode_mouse_move,
    decode_mouse_scroll,
    decode_key_event,
    decode_screen_info,
    decode_switch,
    encode_handshake,
    encode_keepalive,
    encode_screen_info,
    read_packet,
)
from mouseshare.network.tls import generate_cert, server_ssl_context, verify_peer_fingerprint

log = logging.getLogger(__name__)

# Type alias for a packet handler coroutine
PacketHandler = Callable[[int, bytes], Coroutine]


class MouseShareServer:
    """
    Listens for one client connection.  Dispatches incoming packets to
    registered handlers and exposes a `send` method for outgoing packets.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._handlers: dict[int, PacketHandler] = {}
        self._server: asyncio.Server | None = None
        self._connected = asyncio.Event()
        self._peer_screen: tuple[int, int] | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def on(self, msg_type: int) -> Callable:
        """Decorator to register a handler for a specific message type."""
        def decorator(fn: PacketHandler) -> PacketHandler:
            self._handlers[msg_type] = fn
            return fn
        return decorator

    def register(self, msg_type: int, fn: PacketHandler) -> None:
        self._handlers[msg_type] = fn

    async def send(self, frame: bytes) -> None:
        """Send a pre-encoded packet frame to the connected client."""
        if self._writer is None:
            return
        async with self._lock:
            try:
                self._writer.write(frame)
                await self._writer.drain()
            except (ConnectionResetError, BrokenPipeError, OSError) as exc:
                log.warning("Send failed: %s", exc)
                await self._disconnect()

    async def wait_for_client(self) -> None:
        """Block until a client connects."""
        await self._connected.wait()

    @property
    def peer_screen(self) -> tuple[int, int] | None:
        return self._peer_screen

    @property
    def is_connected(self) -> bool:
        return self._writer is not None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start listening.  Call this once; runs until stop() is called."""
        cfg = self.config
        generate_cert(cfg.cert_dir)
        ssl_ctx = server_ssl_context(cfg.cert_dir) if cfg.tls_enabled else None

        self._server = await asyncio.start_server(
            self._handle_connection,
            host=cfg.host,
            port=cfg.port,
            ssl=ssl_ctx,
        )
        addr = self._server.sockets[0].getsockname()
        log.info("MouseShare server listening on %s:%s (TLS=%s)", addr[0], addr[1], cfg.tls_enabled)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        await self._disconnect()

    # ── Connection handling ───────────────────────────────────────────────────

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        log.info("Client connected from %s", peer)

        # Fingerprint check (Trust-On-First-Use)
        if self.config.tls_enabled:
            if not verify_peer_fingerprint(writer, self.config.peer_fingerprint):
                log.warning("Peer fingerprint mismatch — rejecting connection from %s", peer)
                writer.close()
                return

        self._writer = writer
        self._connected.set()

        # Handshake exchange
        await self._do_handshake(writer)

        # Announce our screen dimensions
        from mouseshare.input.screen import get_screen_size
        w, h = get_screen_size()
        await self.send(encode_screen_info(w, h))

        # Start keepalive loop alongside packet reading
        try:
            await asyncio.gather(
                self._read_loop(reader),
                self._keepalive_loop(),
            )
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            log.info("Client %s disconnected", peer)
        finally:
            await self._disconnect()

    async def _do_handshake(self, writer: asyncio.StreamWriter) -> None:
        writer.write(encode_handshake())
        await writer.drain()

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        while True:
            msg_type, payload = await read_packet(reader)

            if msg_type == MSG_DISCONNECT:
                log.info("Client sent graceful disconnect")
                break

            if msg_type == MSG_KEEPALIVE:
                continue  # nothing to do

            if msg_type == MSG_SCREEN_INFO:
                w, h = decode_screen_info(payload)
                self._peer_screen = (w, h)
                log.debug("Client screen size: %dx%d", w, h)
                continue

            if msg_type == MSG_HANDSHAKE:
                info = decode_handshake(payload)
                log.debug("Client handshake: %s", info)
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

    async def _disconnect(self) -> None:
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        self._connected.clear()

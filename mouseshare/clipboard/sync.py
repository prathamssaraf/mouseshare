"""
Clipboard synchronisation — high-level logic that wires the ClipboardMonitor
to the network layer (server or client).

Outgoing: monitor detects change → encode → send packet
Incoming: receive packet → write to local clipboard → mark as sent (no echo)
"""

from __future__ import annotations

import asyncio
import logging

from mouseshare.clipboard.monitor import ClipboardMonitor, write_image, write_text
from mouseshare.network.protocol import encode_clip_image, encode_clip_text

log = logging.getLogger(__name__)


class ClipboardSync:
    """
    Attach to a server or client send function to get full bidirectional
    clipboard synchronisation.

    Usage:
        sync = ClipboardSync(loop, send_fn)
        sync.start()

        # When a clipboard packet arrives from the network:
        await sync.handle_packet(msg_type, payload)
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        send_fn,   # async callable that accepts encoded bytes
    ) -> None:
        self._send = send_fn
        self._monitor = ClipboardMonitor(
            loop=loop,
            on_text=self._on_local_text,
            on_image=self._on_local_image,
        )
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.get_event_loop().create_task(
            self._monitor.run(), name="clipboard-monitor"
        )

    def stop(self) -> None:
        self._monitor.stop()
        if self._task:
            self._task.cancel()

    # ── Outgoing (local → remote) ─────────────────────────────────────────────

    async def _on_local_text(self, text: str) -> None:
        log.debug("Clipboard text changed (%d chars) — sending", len(text))
        await self._send(encode_clip_text(text))

    async def _on_local_image(self, png_bytes: bytes) -> None:
        log.debug("Clipboard image changed (%d bytes) — sending", len(png_bytes))
        await self._send(encode_clip_image(png_bytes))

    # ── Incoming (remote → local) ─────────────────────────────────────────────

    async def handle_text(self, _msg_type: int, payload: bytes) -> None:
        from mouseshare.network.protocol import decode_clip_text
        text = decode_clip_text(payload)
        log.debug("Received clipboard text (%d chars)", len(text))
        self._monitor.mark_sent(text)
        write_text(text)

    async def handle_image(self, _msg_type: int, payload: bytes) -> None:
        from mouseshare.network.protocol import decode_clip_image
        png_bytes = decode_clip_image(payload)
        log.debug("Received clipboard image (%d bytes)", len(png_bytes))
        self._monitor.mark_sent(png_bytes)
        write_image(png_bytes)

"""
File transfer — sender side.

Breaks a file into FILE_CHUNK_SIZE chunks, sends them sequentially, then
sends a final SHA-256 checksum for integrity verification.

The receiver replies with MSG_FILE_NACK if the checksum fails.

Progress is reported via an optional async callback:
    on_progress(bytes_sent: int, total_bytes: int)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional

from mouseshare.constants import FILE_CHUNK_SIZE
from mouseshare.network.protocol import (
    encode_file_chunk,
    encode_file_end,
    encode_file_start,
)

log = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], Awaitable[None]]


class FileSender:
    """
    Sends a single file over the network connection.

    Usage:
        sender = FileSender(send_fn, on_progress=cb)
        success = await sender.send(Path("/path/to/file.pdf"))
    """

    def __init__(
        self,
        send_fn,
        on_progress: Optional[ProgressCallback] = None,
    ) -> None:
        self._send = send_fn
        self._on_progress = on_progress
        self._nack_event = asyncio.Event()
        self._ack_ok = True

    def notify_nack(self) -> None:
        """Call this when a MSG_FILE_NACK is received from the peer."""
        self._ack_ok = False
        self._nack_event.set()

    async def send(self, path: Path) -> bool:
        """
        Send the file at *path*.
        Returns True on success, False if peer reported checksum failure.
        """
        if not path.exists():
            log.error("File not found: %s", path)
            return False

        file_size = path.stat().st_size
        filename  = path.name
        sha256    = hashlib.sha256()

        log.info("Sending file: %s (%d bytes)", filename, file_size)

        # FILE_START
        await self._send(encode_file_start(filename, file_size))

        # FILE_CHUNK stream
        chunk_id  = 0
        bytes_sent = 0
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(FILE_CHUNK_SIZE)
                if not chunk:
                    break
                sha256.update(chunk)
                await self._send(encode_file_chunk(chunk_id, chunk))
                bytes_sent += len(chunk)
                chunk_id   += 1
                if self._on_progress:
                    await self._on_progress(bytes_sent, file_size)
                # Yield to event loop to keep UI responsive
                await asyncio.sleep(0)

        # FILE_END with checksum
        checksum = sha256.digest()
        await self._send(encode_file_end(checksum))
        log.info("File sent: %s — waiting for ACK", filename)

        # Wait up to 10 seconds for a NACK (silence = success)
        try:
            await asyncio.wait_for(self._nack_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            return True   # no NACK received — assume success

        if not self._ack_ok:
            log.error("Peer reported checksum failure for %s", filename)
            return False
        return True

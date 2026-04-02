"""
File transfer — receiver side.

Handles the three-packet sequence:
  MSG_FILE_START  → open a temp file
  MSG_FILE_CHUNK  → write chunk (order guaranteed by TCP)
  MSG_FILE_END    → verify SHA-256, rename to final destination

If the checksum fails, the temp file is deleted and MSG_FILE_NACK is sent.

Files are saved to config.receive_dir (default ~/Downloads/MouseShare/).
If a file with the same name already exists, a counter suffix is appended:
    photo.jpg → photo (1).jpg → photo (2).jpg
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Awaitable, Callable, Optional

from mouseshare.network.protocol import (
    decode_file_chunk,
    decode_file_end,
    decode_file_start,
    encode_file_nack,
)

log = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], Awaitable[None]]
CompleteCallback = Callable[[Path], Awaitable[None]]


def _unique_path(directory: Path, filename: str) -> Path:
    """Return a path that does not already exist, adding (N) suffix if needed."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem   = Path(filename).stem
    suffix = Path(filename).suffix
    n = 1
    while True:
        candidate = directory / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


class FileReceiver:
    """
    Stateful receiver that processes file transfer packets as they arrive.

    One FileReceiver instance handles one file at a time.  After each
    completed (or failed) transfer it resets its state automatically.

    Usage:
        receiver = FileReceiver(receive_dir, send_fn, on_progress=cb, on_complete=cb)

        # Wire into packet dispatcher:
        server.register(MSG_FILE_START,  receiver.handle_start)
        server.register(MSG_FILE_CHUNK,  receiver.handle_chunk)
        server.register(MSG_FILE_END,    receiver.handle_end)
    """

    def __init__(
        self,
        receive_dir: Path,
        send_fn,
        on_progress: Optional[ProgressCallback] = None,
        on_complete: Optional[CompleteCallback]  = None,
    ) -> None:
        receive_dir.mkdir(parents=True, exist_ok=True)
        self._receive_dir = receive_dir
        self._send        = send_fn
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._reset()

    # ── Packet handlers (register these with server/client) ───────────────────

    async def handle_start(self, _msg_type: int, payload: bytes) -> None:
        self._reset()
        self._file_size, self._filename = decode_file_start(payload)
        self._tmp_path = Path(tempfile.mktemp(
            prefix=".ms_recv_", suffix=".tmp", dir=self._receive_dir
        ))
        self._fh = self._tmp_path.open("wb")
        self._sha256 = hashlib.sha256()
        log.info(
            "Receiving file: %s (%d bytes) → %s",
            self._filename, self._file_size, self._tmp_path
        )

    async def handle_chunk(self, _msg_type: int, payload: bytes) -> None:
        if self._fh is None:
            log.warning("FILE_CHUNK received without active transfer — ignoring")
            return
        _chunk_id, data = decode_file_chunk(payload)
        self._fh.write(data)
        self._sha256.update(data)
        self._bytes_received += len(data)
        if self._on_progress:
            await self._on_progress(self._bytes_received, self._file_size)

    async def handle_end(self, _msg_type: int, payload: bytes) -> None:
        if self._fh is None:
            return

        self._fh.close()
        self._fh = None
        expected = decode_file_end(payload)
        actual   = self._sha256.digest()

        if actual != expected:
            log.error("Checksum mismatch for %s — discarding", self._filename)
            self._tmp_path.unlink(missing_ok=True)
            await self._send(encode_file_nack())
            self._reset()
            return

        final_path = _unique_path(self._receive_dir, self._filename)
        self._tmp_path.rename(final_path)
        log.info("File received OK: %s", final_path)

        if self._on_complete:
            await self._on_complete(final_path)

        self._reset()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _reset(self) -> None:
        if hasattr(self, "_fh") and self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass
        self._fh: Optional[object]         = None
        self._tmp_path: Optional[Path]     = None
        self._filename: str                = ""
        self._file_size: int               = 0
        self._bytes_received: int          = 0
        self._sha256                       = hashlib.sha256()

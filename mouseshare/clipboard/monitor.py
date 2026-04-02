"""
Clipboard monitor — polls the system clipboard for changes and calls a
callback when new content is detected.

Deduplication:
  We track a SHA-256 hash of the last content we SENT.  If the clipboard
  changes to something whose hash matches what we just sent, we skip it.
  This prevents the infinite echo loop:
    Mac copies → sends to Win → Win writes clipboard → Win detects change → sends back → ...

Supported content types (in priority order):
  1. Image  (PNG bytes via Pillow)
  2. Text   (UTF-8 string via pyperclip)
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import sys
from typing import Awaitable, Callable, Optional

from mouseshare.constants import CLIP_MAX_IMAGE_BYTES, CLIP_POLL_INTERVAL

log = logging.getLogger(__name__)

OnTextCallback  = Callable[[str],  Awaitable[None]]
OnImageCallback = Callable[[bytes], Awaitable[None]]


class ClipboardMonitor:
    """
    Polls the clipboard every CLIP_POLL_INTERVAL seconds.
    Calls on_text(str) or on_image(png_bytes) when content changes.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_text: OnTextCallback,
        on_image: OnImageCallback,
    ) -> None:
        self._loop      = loop
        self._on_text   = on_text
        self._on_image  = on_image
        self._last_hash = ""
        self._running   = False

    # ── Public ────────────────────────────────────────────────────────────────

    def mark_sent(self, content: bytes | str) -> None:
        """Call this after WE write to the clipboard so we don't echo it back."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        self._last_hash = hashlib.sha256(content).hexdigest()

    async def run(self) -> None:
        """Polling loop — runs until stop() is called."""
        self._running = True
        log.debug("Clipboard monitor started (interval=%.1fs)", CLIP_POLL_INTERVAL)
        while self._running:
            await asyncio.sleep(CLIP_POLL_INTERVAL)
            try:
                await self._check()
            except Exception as exc:
                log.debug("Clipboard check error: %s", exc)

    def stop(self) -> None:
        self._running = False

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _check(self) -> None:
        # Try image first (higher fidelity than text)
        img_bytes = _read_image()
        if img_bytes and len(img_bytes) <= CLIP_MAX_IMAGE_BYTES:
            h = hashlib.sha256(img_bytes).hexdigest()
            if h != self._last_hash:
                self._last_hash = h
                await self._on_image(img_bytes)
                return

        # Fall back to text
        text = _read_text()
        if text:
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if h != self._last_hash:
                self._last_hash = h
                await self._on_text(text)


# ── Platform clipboard readers ────────────────────────────────────────────────

def _read_text() -> Optional[str]:
    try:
        import pyperclip
        text = pyperclip.paste()
        return text if text else None
    except Exception:
        return None


def _read_image() -> Optional[bytes]:
    """Return PNG bytes of the clipboard image, or None if no image present."""
    if sys.platform == "darwin":
        return _read_image_mac()
    if sys.platform == "win32":
        return _read_image_windows()
    return None


def _read_image_mac() -> Optional[bytes]:
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeTIFF, NSPasteboardTypePNG
        from PIL import Image
        import io as _io

        pb = NSPasteboard.generalPasteboard()
        # Try PNG first, then TIFF
        for ptype in (NSPasteboardTypePNG, NSPasteboardTypeTIFF):
            data = pb.dataForType_(ptype)
            if data:
                raw = bytes(data)
                # Convert to PNG via Pillow to normalise format
                img = Image.open(_io.BytesIO(raw))
                buf = _io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
    except Exception as exc:
        log.debug("Mac image clipboard read failed: %s", exc)
    return None


def _read_image_windows() -> Optional[bytes]:
    try:
        import win32clipboard
        from PIL import Image
        import io as _io

        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB):
                data = win32clipboard.GetClipboardData(win32clipboard.CF_DIB)
                img = Image.open(_io.BytesIO(data))
                buf = _io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
        finally:
            win32clipboard.CloseClipboard()
    except Exception as exc:
        log.debug("Windows image clipboard read failed: %s", exc)
    return None


# ── Platform clipboard writers ────────────────────────────────────────────────

def write_text(text: str) -> None:
    try:
        import pyperclip
        pyperclip.copy(text)
    except Exception as exc:
        log.warning("Clipboard text write failed: %s", exc)


def write_image(png_bytes: bytes) -> None:
    if sys.platform == "darwin":
        _write_image_mac(png_bytes)
    elif sys.platform == "win32":
        _write_image_windows(png_bytes)


def _write_image_mac(png_bytes: bytes) -> None:
    try:
        from AppKit import NSPasteboard, NSPasteboardTypePNG
        from Foundation import NSData
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        ns_data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
        pb.setData_forType_(ns_data, NSPasteboardTypePNG)
    except Exception as exc:
        log.warning("Mac image clipboard write failed: %s", exc)


def _write_image_windows(png_bytes: bytes) -> None:
    try:
        import io as _io
        import win32clipboard
        from PIL import Image

        img = Image.open(_io.BytesIO(png_bytes))
        # Windows clipboard needs BMP/DIB format
        buf = _io.BytesIO()
        img.convert("RGB").save(buf, format="BMP")
        bmp_data = buf.getvalue()[14:]   # strip BMP file header, keep DIB

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
        finally:
            win32clipboard.CloseClipboard()
    except Exception as exc:
        log.warning("Windows image clipboard write failed: %s", exc)

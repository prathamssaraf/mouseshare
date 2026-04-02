"""Tests for clipboard deduplication logic."""

import hashlib
import pytest

from mouseshare.clipboard.monitor import ClipboardMonitor


@pytest.mark.asyncio
async def test_mark_sent_prevents_echo():
    """After marking content as sent, the same content should not fire callback."""
    received = []

    async def on_text(text):
        received.append(text)

    async def on_image(img):
        received.append(img)

    import asyncio
    loop = asyncio.get_event_loop()
    monitor = ClipboardMonitor(loop=loop, on_text=on_text, on_image=on_image)

    text = "hello world"
    monitor.mark_sent(text)
    # Simulate the check finding the same content
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert monitor._last_hash == h
    # No callback should have fired
    assert received == []


@pytest.mark.asyncio
async def test_different_content_fires_callback(monkeypatch):
    """Different content from last hash should trigger the callback."""
    received = []

    async def on_text(text):
        received.append(text)

    async def on_image(img):
        received.append(img)

    import asyncio
    import mouseshare.clipboard.monitor as mod

    loop = asyncio.get_event_loop()
    monitor = ClipboardMonitor(loop=loop, on_text=on_text, on_image=on_image)

    # Monkeypatch _read_text to return a known value
    monkeypatch.setattr(mod, "_read_text", lambda: "new clipboard content")
    monkeypatch.setattr(mod, "_read_image", lambda: None)

    monitor._last_hash = "different_hash"
    await monitor._check()
    assert "new clipboard content" in received

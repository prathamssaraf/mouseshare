"""Tests for the file transfer engine — sender and receiver."""

import asyncio
import hashlib
import tempfile
from pathlib import Path

import pytest

from mouseshare.transfer.sender import FileSender
from mouseshare.transfer.receiver import FileReceiver
from mouseshare.constants import MSG_FILE_START, MSG_FILE_CHUNK, MSG_FILE_END, MSG_FILE_NACK


@pytest.fixture
def tmp_recv_dir(tmp_path):
    d = tmp_path / "recv"
    d.mkdir()
    return d


@pytest.fixture
def sample_file(tmp_path):
    f = tmp_path / "sample.bin"
    f.write_bytes(b"Hello MouseShare! " * 4000)  # ~72 KB
    return f


@pytest.mark.asyncio
async def test_send_receive_round_trip(tmp_recv_dir, sample_file):
    """Sender → packets → Receiver should produce an identical file."""
    packets = []

    async def fake_send(frame):
        packets.append(frame)

    received_path = None

    async def on_complete(path):
        nonlocal received_path
        received_path = path

    sender   = FileSender(send_fn=fake_send)
    receiver = FileReceiver(
        receive_dir=tmp_recv_dir,
        send_fn=fake_send,
        on_complete=on_complete,
    )

    # Send
    ok = await sender.send(sample_file)
    assert ok

    # Replay packets through receiver
    import struct
    HEADER_SIZE = 5
    for frame in packets:
        msg_type, length = struct.unpack("!BI", frame[:HEADER_SIZE])
        payload = frame[HEADER_SIZE:HEADER_SIZE + length]
        if msg_type == MSG_FILE_START:
            await receiver.handle_start(msg_type, payload)
        elif msg_type == MSG_FILE_CHUNK:
            await receiver.handle_chunk(msg_type, payload)
        elif msg_type == MSG_FILE_END:
            await receiver.handle_end(msg_type, payload)

    assert received_path is not None
    assert received_path.exists()
    assert received_path.read_bytes() == sample_file.read_bytes()


@pytest.mark.asyncio
async def test_unique_path_collision(tmp_recv_dir, sample_file):
    """Receiving the same filename twice should produce (1) suffix."""
    packets = []

    async def fake_send(frame):
        packets.append(frame)

    paths = []

    async def on_complete(path):
        paths.append(path)

    import struct
    HEADER_SIZE = 5

    async def do_transfer():
        p = []

        async def _send(frame):
            p.append(frame)

        sender = FileSender(send_fn=_send)
        await sender.send(sample_file)

        receiver = FileReceiver(
            receive_dir=tmp_recv_dir,
            send_fn=fake_send,
            on_complete=on_complete,
        )
        for frame in p:
            msg_type, length = struct.unpack("!BI", frame[:HEADER_SIZE])
            payload = frame[HEADER_SIZE:HEADER_SIZE + length]
            if msg_type == MSG_FILE_START:
                await receiver.handle_start(msg_type, payload)
            elif msg_type == MSG_FILE_CHUNK:
                await receiver.handle_chunk(msg_type, payload)
            elif msg_type == MSG_FILE_END:
                await receiver.handle_end(msg_type, payload)

    await do_transfer()
    await do_transfer()

    assert len(paths) == 2
    assert paths[0].name == "sample.bin"
    assert paths[1].name == "sample (1).bin"


@pytest.mark.asyncio
async def test_missing_file_returns_false(tmp_path):
    async def fake_send(frame):
        pass

    sender = FileSender(send_fn=fake_send)
    ok = await sender.send(tmp_path / "nonexistent.txt")
    assert not ok

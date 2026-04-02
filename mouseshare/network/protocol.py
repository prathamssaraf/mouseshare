"""
Wire protocol — encoding and decoding of all MouseShare packets.

Every packet on the wire:
  [1B msg_type] [4B payload_length, big-endian uint32] [payload_length bytes payload]

All multi-byte integers are big-endian.  Coordinates are normalised to
0–65535 so they map correctly across different screen resolutions.
"""

from __future__ import annotations

import struct
from typing import Any

from mouseshare.constants import (
    APP_VERSION,
    CURRENT_PLATFORM,
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
    PROTOCOL_VERSION,
)

# ── Low-level frame helpers ───────────────────────────────────────────────────

HEADER_FMT  = "!BI"   # 1B msg_type + 4B uint32 length
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # == 5


def encode_packet(msg_type: int, payload: bytes = b"") -> bytes:
    """Prepend the 5-byte header to a payload and return the full frame."""
    return struct.pack(HEADER_FMT, msg_type, len(payload)) + payload


async def read_packet(reader: "asyncio.StreamReader") -> tuple[int, bytes]:
    """
    Read exactly one packet from *reader*.
    Returns (msg_type, payload).
    Raises asyncio.IncompleteReadError / ConnectionError on EOF.
    """
    header = await reader.readexactly(HEADER_SIZE)
    msg_type, length = struct.unpack(HEADER_FMT, header)
    payload = await reader.readexactly(length) if length > 0 else b""
    return msg_type, payload


# ── Encoder helpers ───────────────────────────────────────────────────────────

def encode_handshake() -> bytes:
    major, minor, patch = APP_VERSION
    payload = struct.pack("!HHB", PROTOCOL_VERSION, (major << 8) | minor, CURRENT_PLATFORM)
    return encode_packet(MSG_HANDSHAKE, payload)


def encode_screen_info(width: int, height: int) -> bytes:
    return encode_packet(MSG_SCREEN_INFO, struct.pack("!II", width, height))


def encode_switch(direction: int) -> bytes:
    return encode_packet(MSG_SWITCH, struct.pack("!B", direction))


def encode_mouse_move(nx: float, ny: float) -> bytes:
    """nx, ny are normalised 0.0–1.0 floats → packed as uint16 (0–65535)."""
    x = int(max(0.0, min(1.0, nx)) * 65535)
    y = int(max(0.0, min(1.0, ny)) * 65535)
    return encode_packet(MSG_MOUSE_MOVE, struct.pack("!HH", x, y))


def encode_mouse_click(button: int, pressed: bool) -> bytes:
    return encode_packet(MSG_MOUSE_CLICK, struct.pack("!BB", button, int(pressed)))


def encode_mouse_scroll(dx: int, dy: int) -> bytes:
    return encode_packet(MSG_MOUSE_SCROLL, struct.pack("!ii", dx, dy))


def encode_key_event(keycode: int, pressed: bool) -> bytes:
    return encode_packet(MSG_KEY_EVENT, struct.pack("!IB", keycode, int(pressed)))


def encode_clip_text(text: str) -> bytes:
    return encode_packet(MSG_CLIP_TEXT, text.encode("utf-8"))


def encode_clip_image(png_bytes: bytes) -> bytes:
    return encode_packet(MSG_CLIP_IMAGE, png_bytes)


def encode_file_start(filename: str, file_size: int) -> bytes:
    name_bytes = filename.encode("utf-8")
    payload = struct.pack("!QH", file_size, len(name_bytes)) + name_bytes
    return encode_packet(MSG_FILE_START, payload)


def encode_file_chunk(chunk_id: int, data: bytes) -> bytes:
    payload = struct.pack("!I", chunk_id) + data
    return encode_packet(MSG_FILE_CHUNK, payload)


def encode_file_end(checksum: bytes) -> bytes:
    """checksum must be 32 bytes (SHA-256)."""
    return encode_packet(MSG_FILE_END, checksum)


def encode_file_nack() -> bytes:
    return encode_packet(MSG_FILE_NACK)


def encode_drag_start(filename: str) -> bytes:
    name_bytes = filename.encode("utf-8")
    payload = struct.pack("!H", len(name_bytes)) + name_bytes
    return encode_packet(MSG_DRAG_START, payload)


def encode_keepalive() -> bytes:
    return encode_packet(MSG_KEEPALIVE)


def encode_disconnect() -> bytes:
    return encode_packet(MSG_DISCONNECT)


# ── Decoder helpers ───────────────────────────────────────────────────────────

def decode_handshake(payload: bytes) -> dict[str, Any]:
    proto_ver, app_ver, platform = struct.unpack("!HHB", payload)
    return {
        "protocol_version": proto_ver,
        "app_version": app_ver,
        "platform": platform,
    }


def decode_screen_info(payload: bytes) -> tuple[int, int]:
    return struct.unpack("!II", payload)  # (width, height)


def decode_switch(payload: bytes) -> int:
    return struct.unpack("!B", payload)[0]


def decode_mouse_move(payload: bytes) -> tuple[float, float]:
    x, y = struct.unpack("!HH", payload)
    return x / 65535.0, y / 65535.0   # normalised 0.0–1.0


def decode_mouse_click(payload: bytes) -> tuple[int, bool]:
    button, pressed = struct.unpack("!BB", payload)
    return button, bool(pressed)


def decode_mouse_scroll(payload: bytes) -> tuple[int, int]:
    return struct.unpack("!ii", payload)  # (dx, dy)


def decode_key_event(payload: bytes) -> tuple[int, bool]:
    keycode, pressed = struct.unpack("!IB", payload)
    return keycode, bool(pressed)


def decode_clip_text(payload: bytes) -> str:
    return payload.decode("utf-8")


def decode_clip_image(payload: bytes) -> bytes:
    return payload  # raw PNG bytes


def decode_file_start(payload: bytes) -> tuple[int, str]:
    file_size, name_len = struct.unpack("!QH", payload[:10])
    filename = payload[10:10 + name_len].decode("utf-8")
    return file_size, filename


def decode_file_chunk(payload: bytes) -> tuple[int, bytes]:
    chunk_id = struct.unpack("!I", payload[:4])[0]
    return chunk_id, payload[4:]


def decode_file_end(payload: bytes) -> bytes:
    return payload  # 32-byte SHA-256


def decode_drag_start(payload: bytes) -> str:
    name_len = struct.unpack("!H", payload[:2])[0]
    return payload[2:2 + name_len].decode("utf-8")

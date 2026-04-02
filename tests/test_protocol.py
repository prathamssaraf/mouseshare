"""Tests for the wire protocol encode/decode round-trips."""

import pytest
from mouseshare.network.protocol import (
    encode_mouse_move, decode_mouse_move,
    encode_mouse_click, decode_mouse_click,
    encode_mouse_scroll, decode_mouse_scroll,
    encode_key_event, decode_key_event,
    encode_clip_text, decode_clip_text,
    encode_file_start, decode_file_start,
    encode_file_chunk, decode_file_chunk,
    encode_file_end, decode_file_end,
    encode_drag_start, decode_drag_start,
    encode_keepalive, encode_disconnect,
    HEADER_SIZE,
)
from mouseshare.constants import (
    MSG_MOUSE_MOVE, MSG_MOUSE_CLICK, MSG_MOUSE_SCROLL,
    MSG_KEY_EVENT, MSG_CLIP_TEXT, MSG_FILE_START,
    MSG_FILE_CHUNK, MSG_FILE_END, MSG_DRAG_START,
    MSG_KEEPALIVE, MSG_DISCONNECT,
)
import struct


def _unpack(frame):
    msg_type, length = struct.unpack("!BI", frame[:HEADER_SIZE])
    payload = frame[HEADER_SIZE:HEADER_SIZE + length]
    return msg_type, payload


def test_mouse_move_round_trip():
    for nx, ny in [(0.0, 0.0), (1.0, 1.0), (0.5, 0.75), (0.0001, 0.9999)]:
        frame = encode_mouse_move(nx, ny)
        mt, payload = _unpack(frame)
        assert mt == MSG_MOUSE_MOVE
        rx, ry = decode_mouse_move(payload)
        assert abs(rx - nx) < 0.0001
        assert abs(ry - ny) < 0.0001


def test_mouse_move_clamps():
    frame = encode_mouse_move(-0.5, 1.5)
    _, payload = _unpack(frame)
    x, y = decode_mouse_move(payload)
    assert x == 0.0
    assert y == 1.0


def test_mouse_click_round_trip():
    for btn, pressed in [(1, True), (2, False), (3, True)]:
        frame = encode_mouse_click(btn, pressed)
        mt, payload = _unpack(frame)
        assert mt == MSG_MOUSE_CLICK
        rb, rp = decode_mouse_click(payload)
        assert rb == btn
        assert rp == pressed


def test_mouse_scroll_round_trip():
    for dx, dy in [(0, 0), (3, -3), (-100, 100)]:
        frame = encode_mouse_scroll(dx, dy)
        mt, payload = _unpack(frame)
        assert mt == MSG_MOUSE_SCROLL
        rdx, rdy = decode_mouse_scroll(payload)
        assert rdx == dx
        assert rdy == dy


def test_key_event_round_trip():
    for code, pressed in [(65, True), (13, False), (0xFFFF, True)]:
        frame = encode_key_event(code, pressed)
        mt, payload = _unpack(frame)
        assert mt == MSG_KEY_EVENT
        rc, rp = decode_key_event(payload)
        assert rc == code
        assert rp == pressed


def test_clip_text_round_trip():
    for text in ["hello", "こんにちは", "emoji 🎉", ""]:
        frame = encode_clip_text(text)
        mt, payload = _unpack(frame)
        assert mt == MSG_CLIP_TEXT
        assert decode_clip_text(payload) == text


def test_file_start_round_trip():
    for size, name in [(0, "a.txt"), (1_000_000_000, "archive.tar.gz"), (1, "日本語.pdf")]:
        frame = encode_file_start(name, size)
        mt, payload = _unpack(frame)
        assert mt == MSG_FILE_START
        rs, rn = decode_file_start(payload)
        assert rs == size
        assert rn == name


def test_file_chunk_round_trip():
    data = b"\x00\xFF" * 1000
    frame = encode_file_chunk(42, data)
    mt, payload = _unpack(frame)
    assert mt == MSG_FILE_CHUNK
    chunk_id, rdata = decode_file_chunk(payload)
    assert chunk_id == 42
    assert rdata == data


def test_file_end_round_trip():
    checksum = b"\xAB" * 32
    frame = encode_file_end(checksum)
    mt, payload = _unpack(frame)
    assert mt == MSG_FILE_END
    assert decode_file_end(payload) == checksum


def test_drag_start_round_trip():
    name = "photo.jpg"
    frame = encode_drag_start(name)
    mt, payload = _unpack(frame)
    assert mt == MSG_DRAG_START
    assert decode_drag_start(payload) == name


def test_keepalive_has_no_payload():
    frame = encode_keepalive()
    mt, payload = _unpack(frame)
    assert mt == MSG_KEEPALIVE
    assert payload == b""


def test_disconnect_has_no_payload():
    frame = encode_disconnect()
    mt, payload = _unpack(frame)
    assert mt == MSG_DISCONNECT
    assert payload == b""

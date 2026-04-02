# MouseShare Wire Protocol

Version: 1

## Frame Format

Every packet on the wire uses the same 5-byte header:

```
┌─────────────┬──────────────────────────┬──────────────────┐
│  1 byte     │  4 bytes                 │  N bytes         │
│  msg_type   │  payload_length (uint32) │  payload         │
│  (uint8)    │  big-endian              │                  │
└─────────────┴──────────────────────────┴──────────────────┘
```

All multi-byte integers are **big-endian**. All strings are **UTF-8**.

Mouse X/Y coordinates are **normalised** to the range 0–65535 (uint16) so they
map correctly across machines with different screen resolutions.

## Message Types

| Hex  | Name          | Payload layout |
|------|---------------|----------------|
| 0x01 | HANDSHAKE     | `uint16 proto_ver` + `uint16 app_ver` + `uint8 platform` |
| 0x02 | SCREEN_INFO   | `uint32 width` + `uint32 height` |
| 0x03 | SWITCH        | `uint8 direction` |
| 0x04 | MOUSE_MOVE    | `uint16 x` + `uint16 y` (normalised 0–65535) |
| 0x05 | MOUSE_CLICK   | `uint8 button` + `uint8 pressed` (1=down, 0=up) |
| 0x06 | MOUSE_SCROLL  | `int32 dx` + `int32 dy` |
| 0x07 | KEY_EVENT     | `uint32 keycode` + `uint8 pressed` |
| 0x08 | CLIP_TEXT     | UTF-8 bytes |
| 0x09 | CLIP_IMAGE    | PNG bytes |
| 0x0A | FILE_START    | `uint64 file_size` + `uint16 name_len` + filename bytes |
| 0x0B | FILE_CHUNK    | `uint32 chunk_id` + chunk data |
| 0x0C | FILE_END      | 32 bytes SHA-256 checksum |
| 0x0D | FILE_NACK     | (empty) — checksum failed |
| 0x0E | DRAG_START    | `uint16 name_len` + filename bytes |
| 0x0F | KEEPALIVE     | (empty) |
| 0xFF | DISCONNECT    | (empty) — graceful close |

## Direction Values (SWITCH payload)

| Value | Meaning |
|-------|---------|
| 0x01  | LEFT |
| 0x02  | RIGHT |
| 0x03  | TOP |
| 0x04  | BOTTOM |

## Button Values (MOUSE_CLICK payload)

| Value | Meaning |
|-------|---------|
| 0x01  | Left button |
| 0x02  | Right button |
| 0x03  | Middle button |

## Platform IDs (HANDSHAKE payload)

| Value | Platform |
|-------|----------|
| 0x01  | macOS |
| 0x02  | Windows |
| 0x03  | Linux |

## Connection Sequence

```
Client                          Server
  │                               │
  │── TCP connect ────────────────►│
  │◄─ TLS handshake ──────────────│  (if TLS enabled)
  │                               │
  │◄─ HANDSHAKE ──────────────────│  server sends first
  │── HANDSHAKE ──────────────────►│
  │                               │
  │◄─ SCREEN_INFO ────────────────│  server sends its resolution
  │── SCREEN_INFO ────────────────►│  client sends its resolution
  │                               │
  │      ── steady state ──        │
  │◄─ MOUSE_MOVE (stream) ────────│
  │◄─ KEY_EVENT (stream) ─────────│
  │◄─ CLIP_TEXT / CLIP_IMAGE ─────│  when clipboard changes
  │── CLIP_TEXT / CLIP_IMAGE ─────►│  client can also send
  │── FILE_START ──────────────────►│  client initiates file send
  │── FILE_CHUNK × N ─────────────►│
  │── FILE_END ───────────────────►│
  │◄─ FILE_NACK (on error) ───────│  or silence = success
  │◄─ KEEPALIVE (every 5s) ───────│
  │── KEEPALIVE (every 5s) ───────►│
  │                               │
  │── DISCONNECT ─────────────────►│  graceful close
```

## File Transfer Flow

```
Sender                         Receiver
  │                               │
  │── FILE_START ─────────────────►│  filename + total size
  │── FILE_CHUNK (id=0) ──────────►│  first 64 KB chunk
  │── FILE_CHUNK (id=1) ──────────►│
  │   ... (N chunks) ...           │
  │── FILE_END ───────────────────►│  SHA-256 of entire file
  │                               │  receiver verifies checksum
  │                               │  if OK: rename .tmp → final path
  │◄─ FILE_NACK (if bad) ─────────│  only sent on failure
```

## Security

- All traffic is wrapped in TLS (self-signed certificate, generated on first run).
- Trust model: **Trust On First Use (TOFU)** — the peer's certificate fingerprint
  is verified on connection and stored in config after the first successful connection.
- Fingerprints are SHA-256 of the DER-encoded certificate, displayed as hex.
- A short 8-character prefix is shown in the Settings UI for easy verbal verification.

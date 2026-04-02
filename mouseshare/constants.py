"""
Protocol constants, message types, and application-wide defaults.

Wire format for every packet:
  [1 byte: msg_type] [4 bytes: payload_length (big-endian uint32)] [N bytes: payload]

All integers are big-endian.  All strings are UTF-8.
"""

import sys

# ── Application ──────────────────────────────────────────────────────────────
APP_NAME        = "MouseShare"
APP_VERSION     = (0, 1, 0)          # (major, minor, patch)
PROTOCOL_VERSION = 1                  # bumped on breaking wire changes

# ── Network ───────────────────────────────────────────────────────────────────
DEFAULT_PORT      = 24800
DISCOVERY_PORT    = 24801             # UDP broadcast for auto-discovery
KEEPALIVE_INTERVAL = 5.0             # seconds between KEEPALIVE packets
RECONNECT_BASE    = 1.0              # initial reconnect delay (seconds)
RECONNECT_MAX     = 30.0             # maximum reconnect delay (seconds)
READ_TIMEOUT      = 15.0             # seconds before considering connection dead

# ── Message Types (1 byte each) ───────────────────────────────────────────────
MSG_HANDSHAKE    = 0x01   # version negotiation; payload: 2B version + 1B platform
MSG_SCREEN_INFO  = 0x02   # screen dimensions;   payload: 4B width + 4B height
MSG_SWITCH       = 0x03   # focus switch;         payload: 1B direction
MSG_MOUSE_MOVE   = 0x04   # mouse move;           payload: 4B x + 4B y (absolute, 0–65535 normalised)
MSG_MOUSE_CLICK  = 0x05   # mouse button;         payload: 1B button + 1B pressed (1/0)
MSG_MOUSE_SCROLL = 0x06   # scroll wheel;         payload: 4B dx + 4B dy (signed)
MSG_KEY_EVENT    = 0x07   # keyboard;             payload: 4B keycode + 1B pressed (1/0)
MSG_CLIP_TEXT    = 0x08   # clipboard text;       payload: UTF-8 bytes
MSG_CLIP_IMAGE   = 0x09   # clipboard image;      payload: PNG bytes
MSG_FILE_START   = 0x0A   # begin file transfer;  payload: 8B size + 2B name_len + name
MSG_FILE_CHUNK   = 0x0B   # file chunk;           payload: 4B chunk_id + data
MSG_FILE_END     = 0x0C   # end of file;          payload: 32B SHA-256 checksum
MSG_FILE_NACK    = 0x0D   # checksum failed;      payload: (none)
MSG_DRAG_START   = 0x0E   # drag-drop initiated;  payload: 2B name_len + filename
MSG_KEEPALIVE    = 0x0F   # heartbeat;            payload: (none)
MSG_DISCONNECT   = 0xFF   # graceful disconnect;  payload: (none)

# ── Switch Directions (used in MSG_SWITCH payload) ────────────────────────────
DIR_LEFT   = 0x01
DIR_RIGHT  = 0x02
DIR_TOP    = 0x03
DIR_BOTTOM = 0x04

# ── Platform IDs (used in MSG_HANDSHAKE payload) ──────────────────────────────
PLATFORM_MAC     = 0x01
PLATFORM_WINDOWS = 0x02
PLATFORM_LINUX   = 0x03

CURRENT_PLATFORM = (
    PLATFORM_MAC     if sys.platform == "darwin"
    else PLATFORM_WINDOWS if sys.platform == "win32"
    else PLATFORM_LINUX
)

# ── Mouse Buttons ────────────────────────────────────────────────────────────
BTN_LEFT   = 0x01
BTN_RIGHT  = 0x02
BTN_MIDDLE = 0x03

# ── File Transfer ─────────────────────────────────────────────────────────────
FILE_CHUNK_SIZE  = 65536    # 64 KB per chunk
FILE_RECV_SUBDIR = "MouseShare"   # created inside ~/Downloads/

# ── Screen Edge Detection ─────────────────────────────────────────────────────
EDGE_THRESHOLD = 3          # pixels from edge that trigger a switch

# ── Clipboard ─────────────────────────────────────────────────────────────────
CLIP_POLL_INTERVAL = 0.5    # seconds between clipboard polls
CLIP_MAX_IMAGE_BYTES = 50 * 1024 * 1024   # 50 MB image cap

# ── TLS / Security ───────────────────────────────────────────────────────────
CERT_DIR_NAME  = ".mouseshare"    # inside user's home directory
CERT_FILE      = "server.crt"
KEY_FILE       = "server.key"
CERT_DAYS_VALID = 3650            # 10 years — self-signed, personal use

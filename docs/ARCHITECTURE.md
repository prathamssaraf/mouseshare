# MouseShare Architecture

## Overview

MouseShare is a LAN-based software KVM with clipboard and file transfer.
Both machines run the same application; one is configured as **server**
(the machine with the physical keyboard/mouse) and one as **client**.

## Component Map

```
┌───────────────────────────────────────────────────────────────────────┐
│                          main.py — Session                            │
│                                                                       │
│   ┌────────────┐   ┌──────────────┐   ┌──────────────┐               │
│   │  TrayIcon  │   │ ClipboardSync│   │ FileReceiver │               │
│   │ (pystray)  │   │ (monitor +   │   │ (chunked TCP)│               │
│   │ daemon thd │   │  sync)       │   │              │               │
│   └────────────┘   └──────┬───────┘   └──────┬───────┘               │
│                           │                   │                       │
│   ┌────────────┐   ┌──────▼───────────────────▼───────┐               │
│   │InputCapture│   │        Network Layer              │               │
│   │(pynput thds│──►│  MouseShareServer / Client        │               │
│   │ Mac+Win)   │   │  asyncio TCP + TLS                │               │
│   └────────────┘   └──────────────────────────────────┘               │
│                                                                       │
│   ┌────────────┐   ┌──────────────┐                                   │
│   │InputInject │   │ DragDrop     │                                   │
│   │(pynput     │   │ Mac: NSPaste │                                   │
│   │ Win+Mac)   │   │ Win: notify  │                                   │
│   └────────────┘   └──────────────┘                                   │
└───────────────────────────────────────────────────────────────────────┘
```

## Threading Model

```
Main thread:  asyncio event loop
              ├── network server / client tasks
              ├── clipboard monitor task
              ├── file transfer tasks
              └── drag-drop async callbacks

Daemon threads:
  ms-mouse-capture    pynput mouse Listener (posts to event loop)
  ms-keyboard-capture pynput keyboard Listener (posts to event loop)
  ms-tray             pystray icon (calls back via threading)
  ms-dragdrop-mac     NSPasteboard poller (posts to event loop)
  ms-progress         Tkinter progress window (one per transfer)
```

**Key rule:** pynput listeners run in daemon threads and post events back to
the asyncio loop using `asyncio.run_coroutine_threadsafe`. They never call
asyncio primitives directly.

## Data Flow — Mouse Move (Server → Client)

```
1. Physical mouse moves on Mac
2. pynput (ms-mouse-capture thread) fires on_move(x, y)
3. InputCapture._on_move() checks if forwarding is active
4. If yes: encode_mouse_move(nx, ny) → bytes
5. asyncio.run_coroutine_threadsafe(server.send(frame), loop)
6. asyncio loop: frame sent over TLS TCP to Windows client
7. Client read_loop receives packet, calls _h_move handler
8. inject_mouse_move(nx, ny) → pynput Controller → SendInput on Windows
```

Latency budget on a home WiFi:
- TCP round-trip: ~1–3 ms
- pynput + asyncio overhead: ~0.5 ms
- Total: **~2–5 ms** — imperceptible to users

## Data Flow — File Transfer

```
1. User: right-click tray → "Send File..." → picks file
2. _pick_and_send_file() opens file dialog (Tk, daemon thread)
3. asyncio.run_coroutine_threadsafe(_do_send(), loop)
4. FileSender.send(path):
   a. Sends FILE_START (filename + size)
   b. Reads 64 KB chunks → sends FILE_CHUNK packets
   c. Sends FILE_END (SHA-256)
5. FileReceiver on the peer:
   a. handle_start → opens .tmp file
   b. handle_chunk → writes data, updates progress
   c. handle_end → verifies SHA-256, renames to final path
   d. on_complete → shows OS notification
```

## Security Model

- **Transport:** TLS 1.2+ with a self-signed RSA-2048 certificate generated
  on first run and stored in `~/.mouseshare/certs/`.
- **Trust:** Trust-On-First-Use (TOFU). The peer's certificate fingerprint
  (SHA-256) is stored in config after the first verified connection.
- **Scope:** All traffic stays on the local network. No cloud, no relay servers.
- **Permissions needed:**
  - macOS: Accessibility (for CGEventTap via pynput)
  - Windows: Firewall allow on port 24800

## Config File

Stored at `~/.mouseshare/config.json`. Human-readable JSON. Example:

```json
{
  "role": "server",
  "host": "0.0.0.0",
  "port": 24800,
  "other_screen_direction": 2,
  "receive_dir": "/Users/alice/Downloads/MouseShare",
  "clipboard_sync": true,
  "file_transfer": true,
  "drag_drop": true,
  "auto_discover": true,
  "start_on_login": false,
  "tls_enabled": true,
  "peer_fingerprint": "A1B2C3D4..."
}
```

# MouseShare

> **Share one mouse, keyboard, clipboard, and files between your Mac and Windows PC — free, open source, no accounts, no subscriptions, no limits.**

Built as a fully open alternative to paid tools like ShareMouse and Mouse Without Borders (Windows-only). Works entirely on your local network — no cloud, no relay servers.

---

## Features

| | Feature | Notes |
|-|---------|-------|
| ✅ | Mouse sharing | Move cursor off screen edge to switch machines |
| ✅ | Keyboard sharing | Keyboard follows mouse automatically |
| ✅ | Text clipboard sync | Copy on Mac, paste on Windows (and vice versa) |
| ✅ | Image clipboard sync | Screenshots and images sync across machines |
| ✅ | File transfer | Send files via tray menu with progress bar |
| ✅ | Drag-and-drop file transfer | Drag files toward the other screen on Mac |
| ✅ | TLS encryption | All traffic encrypted, self-signed cert + fingerprint verification |
| ✅ | System tray icon | Green/red connection indicator, menu-driven |
| ✅ | Settings UI | Configure layout, port, receive folder, and more |
| 🔜 | Auto LAN discovery | Find the peer automatically without typing an IP |

---

## Supported Platforms

| Platform | Version | Architecture |
|----------|---------|-------------|
| macOS | 13 Ventura or later (tested on 26 Tahoe) | Apple Silicon + Intel |
| Windows | 10 (22H2+) or later | x64 |

---

## How It Works

Both machines run the same app. One is the **server** (has the physical mouse and keyboard), the other is the **client** (receives input).

```
┌─────────────────────┐         LAN (TLS TCP)        ┌─────────────────────┐
│   Mac  (server)     │◄──────────────────────────────►│  Windows (client)   │
│                     │                               │                     │
│  Physical mouse ────┼──── mouse events ─────────────┼──► injected cursor  │
│  Physical keyboard ─┼──── key events ───────────────┼──► injected keys    │
│  Clipboard ─────────┼──── clipboard sync ───────────┼──► clipboard        │
│  File drag ─────────┼──── file transfer ────────────┼──► ~/Downloads/     │
└─────────────────────┘                               └─────────────────────┘
```

Mouse coordinates are normalised (0–1) before sending so they map correctly across different screen resolutions. See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the full wire protocol.

---

## Quick Start

### 1. Install Python 3.12

Download from [python.org](https://www.python.org/downloads/) — install on both machines.

### 2. Clone and install dependencies

**On Mac:**
```bash
git clone https://github.com/prathamssaraf/mouseshare
cd mouseshare
pip install -r requirements-mac.txt
```

**On Windows:**
```bat
git clone https://github.com/prathamssaraf/mouseshare
cd mouseshare
pip install -r requirements-win.txt
```

### 3. Grant Accessibility permission (Mac only — one time)

System Settings → Privacy & Security → Accessibility → add Terminal or Python.

Full step-by-step guide: [docs/PERMISSIONS.md](docs/PERMISSIONS.md)

### 4. Find your Mac's IP address

```bash
ipconfig getifaddr en0
```

Example: `192.168.1.42`

### 5. Start the server on Mac

```bash
python -m mouseshare --server
```

### 6. Start the client on Windows

```bat
python -m mouseshare --client --host 192.168.1.42
```

The tray icon turns **green** on both machines when connected.

### 7. Use it

- **Switch to Windows:** Move mouse to the right edge of the Mac screen
- **Switch back to Mac:** Move mouse to the left edge of the Windows screen
- **Send a file:** Right-click tray icon → Send File...
- **Drag a file (Mac → Windows):** Drag a file toward the Windows screen edge on Mac

---

## CLI Options

```
python -m mouseshare [options]

  --server       Run as server (machine with the physical mouse/keyboard)
  --client       Run as client (machine receiving input)
  --host IP      Server IP address (required in client mode)
  --port N       Port number (default: 24800)
  --no-tls       Disable TLS encryption (for local testing only)
  --debug        Verbose logging
  --version      Show version
```

---

## Configuration

Right-click the tray icon → **Settings** to configure:

| Setting | Description |
|---------|-------------|
| Role | Server or Client |
| Host / IP | Server bind address or client target IP |
| Port | TCP port (default 24800) |
| Screen edge | Which edge of this screen leads to the other machine |
| Receive folder | Where incoming files are saved (default: ~/Downloads/MouseShare/) |
| Clipboard sync | Enable/disable clipboard synchronisation |
| File transfer | Enable/disable file transfer |
| Drag and drop | Enable/disable drag-and-drop file transfer |
| Start on login | Launch automatically at login |
| Peer fingerprint | TLS certificate fingerprint of the peer (set automatically on first connect) |

Settings are saved to `~/.mouseshare/config.json`.

---

## Building Packaged Apps

No Python installation required on the target machine after packaging.

**macOS (.app):**
```bash
bash build/build_mac.sh
# Output: dist/MouseShare.app — drag to /Applications
```

**Windows (.exe):**
```bat
build\build_win.bat
REM Output: dist\MouseShare.exe — run directly
```

---

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

Tests cover the wire protocol, file transfer engine, clipboard deduplication, and screen geometry — no network connection or OS permissions required.

---

## Project Structure

```
mouseshare/
├── constants.py          # Protocol constants, message types
├── config.py             # Persistent settings (~/.mouseshare/config.json)
├── main.py               # Entry point, component wiring
├── network/
│   ├── tls.py            # TLS cert generation + fingerprint verification
│   ├── protocol.py       # Binary wire protocol encode/decode
│   ├── server.py         # asyncio TCP server
│   └── client.py         # asyncio TCP client with reconnection
├── input/
│   ├── screen.py         # Screen resolution, edge detection, coord normalisation
│   ├── capture.py        # Global mouse/keyboard capture (pynput)
│   └── inject.py         # Mouse/keyboard injection (pynput)
├── clipboard/
│   ├── monitor.py        # Clipboard polling with echo-loop prevention
│   └── sync.py           # Bidirectional clipboard synchronisation
├── transfer/
│   ├── sender.py         # Chunked file sender with SHA-256 integrity
│   └── receiver.py       # Chunked file receiver with checksum verification
├── dragdrop/
│   ├── mac_detector.py   # NSPasteboard drag detection (macOS)
│   └── win_target.py     # Windows toast notification on file receive
└── ui/
    ├── tray.py           # System tray icon (pystray)
    ├── settings.py       # Settings window (tkinter)
    └── progress.py       # File transfer progress bar (tkinter)
```

---

## Security

- All traffic is encrypted with **TLS** (self-signed RSA-2048 certificate generated on first run)
- **Trust On First Use (TOFU):** peer certificate fingerprint is verified and stored on first connection
- All data stays on your **local network** — no internet connection required, no servers involved
- The TLS certificate fingerprint is shown in Settings for manual verification

---

## Dependencies

| Library | Purpose | Platforms |
|---------|---------|----------|
| `pynput` | Mouse/keyboard capture + injection | Mac + Windows |
| `pyperclip` | Text clipboard read/write | Mac + Windows |
| `Pillow` | Image clipboard handling | Mac + Windows |
| `pystray` | System tray icon | Mac + Windows |
| `cryptography` | TLS certificate generation | Mac + Windows |
| `pyobjc` | NSPasteboard drag detection | Mac only |
| `uvloop` | Faster asyncio event loop | Mac only |
| `pywin32` | Windows clipboard + notifications | Windows only |

---

## Comparison with Alternatives

| App | Free | Open Source | Mac↔Win | File Transfer | Drag & Drop |
|-----|------|------------|---------|--------------|------------|
| **MouseShare (this)** | ✅ | ✅ | ✅ | ✅ | ✅ (Mac→Win) |
| ShareMouse | Partial (2 computers) | ❌ | ✅ | ❌ (paid) | ❌ (paid) |
| Mouse Without Borders | ✅ | ✅ | ❌ Win-only | ❌ | ❌ |
| Deskflow / Input Leap | ✅ | ✅ | ✅ | ❌ (removed) | ❌ |
| Synergy | ❌ | Partial | ✅ | ❌ | ❌ |

---

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for development setup, code style, and PR guidelines.

## License

[MIT](LICENSE) — use it, fork it, build on it.

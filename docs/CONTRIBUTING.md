# Contributing to MouseShare

Thank you for considering a contribution!

## Development Setup

```bash
git clone https://github.com/your-org/mouseshare
cd mouseshare

python3.12 -m venv venv
source venv/bin/activate          # macOS / Linux
venv\Scripts\activate             # Windows

pip install -e ".[dev]"

# Platform extras:
pip install -r requirements-mac.txt    # macOS
pip install -r requirements-win.txt    # Windows
```

## Running in Development

```bash
# Mac (server):
python -m mouseshare --server --debug

# Windows (client):
python -m mouseshare --client --host 192.168.1.X --debug
```

## Running Tests

```bash
pytest tests/ -v
```

Tests do not require a real network connection or OS-level input permissions —
they test the protocol encode/decode, file transfer logic, and clipboard
deduplication in isolation.

## Code Style

- Formatter: `black` (line length 100)
- Linter: `ruff`
- Run both before committing: `black . && ruff check .`

## Project Layout

```
mouseshare/
├── constants.py      # All magic numbers and message types
├── config.py         # User settings (JSON)
├── main.py           # Entry point + Session wiring
├── network/          # TCP server, client, protocol, TLS
├── input/            # Mouse/keyboard capture and injection
├── clipboard/        # Clipboard monitoring and sync
├── transfer/         # File sender and receiver
├── dragdrop/         # Platform-specific drag-and-drop
└── ui/               # Tray icon, settings window, progress bar
```

## Adding a New Feature

1. Add any new message types to `constants.py`
2. Add encode/decode functions to `network/protocol.py`
3. Add tests in `tests/`
4. Register handlers in `main.py`

## Platform-Specific Code

Guard all platform-specific imports:
```python
if sys.platform == "darwin":
    from mouseshare.dragdrop.mac_detector import MacDragDropDetector
elif sys.platform == "win32":
    from mouseshare.dragdrop.win_target import notify_file_received
```

Never import `pyobjc` on Windows or `pywin32` on Mac.

## Pull Request Guidelines

- One feature or fix per PR
- Include tests for new behaviour
- Update `docs/PROTOCOL.md` if you change the wire format (bump `PROTOCOL_VERSION`)
- Keep PRs focused — no unrelated refactors

## Reporting Issues

Please include:
- OS and version (macOS 26 Tahoe, Windows 10 22H2, etc.)
- Python version (`python --version`)
- Full error output (run with `--debug`)
- Steps to reproduce

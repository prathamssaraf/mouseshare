"""
Persistent configuration — read/written as JSON to ~/.mouseshare/config.json.

Usage:
    cfg = Config.load()
    cfg.host = "192.168.1.5"
    cfg.save()
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mouseshare.constants import DEFAULT_PORT, DIR_RIGHT


def _config_dir() -> Path:
    """Return (and create if needed) the per-user config directory."""
    p = Path.home() / ".mouseshare"
    p.mkdir(exist_ok=True)
    return p


@dataclass
class Config:
    # ── Network ───────────────────────────────────────────────────────────────
    role: str = "server"               # "server" | "client"
    host: str = "0.0.0.0"             # server: bind address; client: server IP
    port: int = DEFAULT_PORT

    # ── Layout ────────────────────────────────────────────────────────────────
    # Which edge of THIS screen leads to the other machine.
    # Value is one of the DIR_* constants (1–4).
    other_screen_direction: int = DIR_RIGHT

    # ── File Transfer ─────────────────────────────────────────────────────────
    receive_dir: str = field(default_factory=lambda: str(
        Path.home() / "Downloads" / "MouseShare"
    ))

    # ── Features ──────────────────────────────────────────────────────────────
    clipboard_sync: bool = True
    file_transfer: bool = True
    drag_drop: bool = True
    auto_discover: bool = True         # UDP broadcast discovery

    # ── Startup ───────────────────────────────────────────────────────────────
    start_on_login: bool = False

    # ── TLS ───────────────────────────────────────────────────────────────────
    tls_enabled: bool = True
    # Fingerprint of the peer's certificate, set after first verified connection
    peer_fingerprint: str = ""

    # ── Internal ─────────────────────────────────────────────────────────────
    _path: Path = field(default_factory=lambda: _config_dir() / "config.json",
                        compare=False, repr=False)

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> "Config":
        path = _config_dir() / "config.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                data.pop("_path", None)
                valid = {f for f in cls.__dataclass_fields__ if not f.startswith("_")}
                filtered = {k: v for k, v in data.items() if k in valid}
                obj = cls(**filtered)
                obj._path = path
                return obj
            except Exception:
                pass
        obj = cls()
        obj._path = path
        return obj

    def save(self) -> None:
        data = asdict(self)
        data.pop("_path", None)
        self._path.write_text(json.dumps(data, indent=2))

    @property
    def config_dir(self) -> Path:
        return _config_dir()

    @property
    def cert_dir(self) -> Path:
        p = _config_dir() / "certs"
        p.mkdir(exist_ok=True)
        return p

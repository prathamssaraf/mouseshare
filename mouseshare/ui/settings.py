"""
Settings window — a simple tkinter dialog for configuring MouseShare.

Opens in its own Tk window (does not require a running Tk main loop elsewhere).
Saves changes to Config on "Apply".
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from mouseshare.config import Config
from mouseshare.constants import DIR_BOTTOM, DIR_LEFT, DIR_RIGHT, DIR_TOP
from mouseshare.network.tls import get_fingerprint, short_fingerprint

_DIR_LABELS = {
    DIR_RIGHT:  "Right",
    DIR_LEFT:   "Left",
    DIR_TOP:    "Top",
    DIR_BOTTOM: "Bottom",
}
_LABEL_TO_DIR = {v: k for k, v in _DIR_LABELS.items()}


def open_settings(config: Config, on_save=None) -> None:
    """
    Open the settings window.  Blocks until the window is closed.
    Calls on_save(config) if the user clicks Apply.
    """
    root = tk.Tk()
    root.title("MouseShare — Settings")
    root.resizable(False, False)
    root.geometry("480x460")

    try:
        _SettingsUI(root, config, on_save)
        root.mainloop()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


class _SettingsUI:
    def __init__(self, root: tk.Tk, config: Config, on_save) -> None:
        self._root    = root
        self._config  = config
        self._on_save = on_save
        self._build()

    def _build(self) -> None:
        cfg = self._config
        pad = {"padx": 12, "pady": 6}

        # ── Network ───────────────────────────────────────────────────────────
        net_frame = ttk.LabelFrame(self._root, text="Network", padding=8)
        net_frame.pack(fill="x", **pad)

        ttk.Label(net_frame, text="Role:").grid(row=0, column=0, sticky="w")
        self._role = tk.StringVar(value=cfg.role.capitalize())
        role_cb    = ttk.Combobox(
            net_frame, textvariable=self._role, values=["Server", "Client"],
            state="readonly", width=10,
        )
        role_cb.grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(net_frame, text="Host / IP:").grid(row=1, column=0, sticky="w")
        self._host = tk.StringVar(value=cfg.host)
        ttk.Entry(net_frame, textvariable=self._host, width=22).grid(
            row=1, column=1, sticky="w", padx=4
        )

        ttk.Label(net_frame, text="Port:").grid(row=2, column=0, sticky="w")
        self._port = tk.StringVar(value=str(cfg.port))
        ttk.Entry(net_frame, textvariable=self._port, width=8).grid(
            row=2, column=1, sticky="w", padx=4
        )

        # ── Layout ────────────────────────────────────────────────────────────
        layout_frame = ttk.LabelFrame(self._root, text="Screen Layout", padding=8)
        layout_frame.pack(fill="x", **pad)

        ttk.Label(
            layout_frame,
            text="Which edge of THIS screen leads to the other machine?",
            wraplength=420,
        ).pack(anchor="w")
        self._direction = tk.StringVar(
            value=_DIR_LABELS.get(cfg.other_screen_direction, "Right")
        )
        for label in _DIR_LABELS.values():
            ttk.Radiobutton(
                layout_frame, text=label, variable=self._direction, value=label
            ).pack(anchor="w")

        # ── File Transfer ──────────────────────────────────────────────────────
        ft_frame = ttk.LabelFrame(self._root, text="File Transfer", padding=8)
        ft_frame.pack(fill="x", **pad)

        ttk.Label(ft_frame, text="Receive folder:").grid(row=0, column=0, sticky="w")
        self._recv_dir = tk.StringVar(value=cfg.receive_dir)
        ttk.Entry(ft_frame, textvariable=self._recv_dir, width=28).grid(
            row=0, column=1, padx=4
        )
        ttk.Button(ft_frame, text="Browse…", command=self._browse_recv_dir).grid(
            row=0, column=2
        )

        # ── Features ──────────────────────────────────────────────────────────
        feat_frame = ttk.LabelFrame(self._root, text="Features", padding=8)
        feat_frame.pack(fill="x", **pad)

        self._clip   = tk.BooleanVar(value=cfg.clipboard_sync)
        self._files  = tk.BooleanVar(value=cfg.file_transfer)
        self._drag   = tk.BooleanVar(value=cfg.drag_drop)
        self._disc   = tk.BooleanVar(value=cfg.auto_discover)
        self._login  = tk.BooleanVar(value=cfg.start_on_login)

        ttk.Checkbutton(feat_frame, text="Clipboard sync",        variable=self._clip).pack(anchor="w")
        ttk.Checkbutton(feat_frame, text="File transfer",         variable=self._files).pack(anchor="w")
        ttk.Checkbutton(feat_frame, text="Drag-and-drop files",   variable=self._drag).pack(anchor="w")
        ttk.Checkbutton(feat_frame, text="Auto-discover on LAN",  variable=self._disc).pack(anchor="w")
        ttk.Checkbutton(feat_frame, text="Start on login",        variable=self._login).pack(anchor="w")

        # ── TLS fingerprint ────────────────────────────────────────────────────
        tls_frame = ttk.LabelFrame(self._root, text="Security", padding=8)
        tls_frame.pack(fill="x", **pad)
        try:
            fp = short_fingerprint(self._config.cert_dir)
            ttk.Label(tls_frame, text=f"Your fingerprint (share with peer):  {fp}").pack(anchor="w")
        except Exception:
            ttk.Label(tls_frame, text="TLS certificate not yet generated").pack(anchor="w")

        ttk.Label(tls_frame, text="Peer fingerprint:").pack(anchor="w")
        self._peer_fp = tk.StringVar(value=cfg.peer_fingerprint)
        ttk.Entry(tls_frame, textvariable=self._peer_fp, width=36).pack(anchor="w", padx=4)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self._root)
        btn_frame.pack(fill="x", padx=12, pady=10)
        ttk.Button(btn_frame, text="Cancel", command=self._root.destroy).pack(
            side="right", padx=4
        )
        ttk.Button(btn_frame, text="Apply", command=self._apply).pack(side="right")

    def _browse_recv_dir(self) -> None:
        d = filedialog.askdirectory(
            initialdir=self._recv_dir.get(), title="Choose receive folder"
        )
        if d:
            self._recv_dir.set(d)

    def _apply(self) -> None:
        cfg = self._config
        cfg.role                   = self._role.get().lower()
        cfg.host                   = self._host.get().strip()
        try:
            cfg.port               = int(self._port.get())
        except ValueError:
            pass
        cfg.other_screen_direction = _LABEL_TO_DIR.get(self._direction.get(), DIR_RIGHT)
        cfg.receive_dir            = self._recv_dir.get()
        cfg.clipboard_sync         = self._clip.get()
        cfg.file_transfer          = self._files.get()
        cfg.drag_drop              = self._drag.get()
        cfg.auto_discover          = self._disc.get()
        cfg.start_on_login         = self._login.get()
        cfg.peer_fingerprint       = self._peer_fp.get().strip()
        cfg.save()
        if self._on_save:
            self._on_save(cfg)
        self._root.destroy()

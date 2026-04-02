"""
File transfer progress window — shown during send and receive.

Displays:
  • Filename
  • Progress bar (percentage)
  • Transfer speed (MB/s)
  • ETA

Thread-safe: update() can be called from any thread.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Optional


class ProgressWindow:
    """
    A non-blocking progress window for file transfers.

    Usage:
        win = ProgressWindow("Sending photo.jpg", total_bytes=5_000_000)
        win.show()
        win.update(bytes_done=1_000_000)
        win.close()
    """

    def __init__(self, title: str, filename: str, total_bytes: int) -> None:
        self._filename    = filename
        self._total       = total_bytes
        self._root: Optional[tk.Tk] = None
        self._bar: Optional[ttk.Progressbar] = None
        self._label_speed: Optional[tk.StringVar] = None
        self._label_done: Optional[tk.StringVar]  = None
        self._start_time  = time.monotonic()
        self._closed      = False
        self._title       = title
        self._thread: Optional[threading.Thread] = None

    def show(self) -> None:
        """Open the window in its own daemon thread."""
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="ms-progress"
        )
        self._thread.start()

    def update(self, bytes_done: int) -> None:
        """Thread-safe progress update."""
        if self._closed or self._root is None:
            return
        elapsed = max(time.monotonic() - self._start_time, 0.001)
        speed   = bytes_done / elapsed          # bytes/sec
        pct     = (bytes_done / self._total * 100) if self._total else 0
        eta     = (self._total - bytes_done) / speed if speed > 0 else 0

        def _update():
            if self._bar and not self._closed:
                self._bar["value"] = pct
                self._label_done.set(
                    f"{_fmt_bytes(bytes_done)} / {_fmt_bytes(self._total)}"
                )
                self._label_speed.set(
                    f"{_fmt_bytes(speed)}/s  •  ETA {int(eta)}s"
                )
        if self._root:
            try:
                self._root.after(0, _update)
            except Exception:
                pass

    def close(self) -> None:
        self._closed = True
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self) -> None:
        self._root = tk.Tk()
        self._root.title(self._title)
        self._root.resizable(False, False)
        self._root.geometry("420x160")
        self._root.attributes("-topmost", True)

        ttk.Label(self._root, text=self._filename, font=("", 11, "bold")).pack(
            padx=16, pady=(16, 4)
        )

        self._bar = ttk.Progressbar(
            self._root, orient="horizontal", length=380, mode="determinate"
        )
        self._bar.pack(padx=16, pady=4)

        self._label_done  = tk.StringVar(value="0 B / " + _fmt_bytes(self._total))
        self._label_speed = tk.StringVar(value="—")
        ttk.Label(self._root, textvariable=self._label_done).pack()
        ttk.Label(self._root, textvariable=self._label_speed, foreground="gray").pack()

        ttk.Button(self._root, text="Cancel", command=self.close).pack(pady=8)

        self._root.protocol("WM_DELETE_WINDOW", self.close)
        self._root.mainloop()


def _fmt_bytes(b: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"

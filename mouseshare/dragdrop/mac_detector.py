"""
Drag-and-drop detector — macOS side.

Strategy:
  1. Poll NSPasteboard.changeCount() every 100 ms.
  2. When it changes during an active mouse drag (left button held),
     read file URLs from the pasteboard's NSFilenamesPboardType.
  3. If files are found AND the cursor is within EDGE_THRESHOLD pixels of
     the configured screen edge, initiate a file transfer and suppress the
     normal mouse-switch until the transfer starts.

Requires: pyobjc-framework-Cocoa  (macOS only)

This module is imported only on macOS; the import is guarded in the caller.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

log = logging.getLogger(__name__)

POLL_INTERVAL = 0.1   # seconds


class MacDragDropDetector:
    """
    Monitors NSPasteboard for drag events that cross the screen edge.

    Usage:
        detector = MacDragDropDetector(loop, edge_direction, on_drag_files)
        detector.start()
        ...
        detector.stop()
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        edge_direction: int,
        on_drag_files: Callable[[List[Path]], Awaitable[None]],
    ) -> None:
        self._loop          = loop
        self._edge_direction = edge_direction
        self._on_drag_files = on_drag_files
        self._running       = False
        self._thread: Optional[threading.Thread] = None
        self._last_change_count: Optional[int]   = None

    def start(self) -> None:
        self._running = True
        self._thread  = threading.Thread(
            target=self._poll_loop, daemon=True, name="ms-dragdrop-mac"
        )
        self._thread.start()
        log.debug("Mac drag-drop detector started")

    def stop(self) -> None:
        self._running = False

    def set_edge_direction(self, direction: int) -> None:
        self._edge_direction = direction

    # ── Internal ──────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        try:
            from AppKit import NSPasteboard
            from pynput import mouse as ms

            pb         = NSPasteboard.generalPasteboard()
            mouse_ctrl = ms.Controller()

            while self._running:
                count = pb.changeCount()

                if self._last_change_count is not None and count != self._last_change_count:
                    # Pasteboard changed — check if it's a file drag
                    files = self._read_files(pb)
                    if files:
                        # Check if mouse is near the trigger edge
                        from mouseshare.input.screen import detect_edge
                        pos  = mouse_ctrl.position
                        edge = detect_edge(int(pos[0]), int(pos[1]))
                        if edge == self._edge_direction:
                            log.info(
                                "Drag of %d file(s) detected at edge %d",
                                len(files), edge
                            )
                            asyncio.run_coroutine_threadsafe(
                                self._on_drag_files([Path(f) for f in files]),
                                self._loop,
                            )

                self._last_change_count = count
                time.sleep(POLL_INTERVAL)

        except ImportError:
            log.warning("pyobjc not available — drag-drop detection disabled on Mac")
        except Exception as exc:
            log.error("Drag-drop detector error: %s", exc)

    @staticmethod
    def _read_files(pb) -> List[str]:
        """Extract file paths from the general pasteboard."""
        try:
            # NSFilenamesPboardType is the classic drag type
            NSFilenamesPboardType = "NSFilenamesPboardType"
            items = pb.propertyListForType_(NSFilenamesPboardType)
            if items:
                return list(items)
            # Modern NSURL-based drag
            from AppKit import NSURL
            urls = pb.readObjectsForClasses_options_([NSURL], {})
            if urls:
                return [u.path() for u in urls if u.isFileURL()]
        except Exception:
            pass
        return []

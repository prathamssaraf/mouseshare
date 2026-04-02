"""
MouseShare — entry point.

Usage:
    python -m mouseshare               # loads config, starts GUI tray
    python -m mouseshare --server      # force server role
    python -m mouseshare --client      # force client role
    python -m mouseshare --host IP     # set server IP (client role)
    python -m mouseshare --port N      # override port
    python -m mouseshare --no-tls      # disable TLS (dev/testing)
    python -m mouseshare --debug       # verbose logging

Architecture:
  • One asyncio event loop runs on the main thread.
  • pynput listeners (input capture) run in daemon threads and post events
    back to the loop via run_coroutine_threadsafe.
  • The tray icon runs in its own daemon thread (pystray requirement).
  • Clipboard monitor runs as an asyncio Task on the main loop.
  • File transfers run as asyncio Tasks on the main loop.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

from mouseshare import __version__
from mouseshare.config import Config
from mouseshare.constants import (
    CURRENT_PLATFORM,
    DIR_LEFT, DIR_RIGHT, DIR_TOP, DIR_BOTTOM,
    MSG_CLIP_IMAGE,
    MSG_CLIP_TEXT,
    MSG_FILE_CHUNK,
    MSG_FILE_END,
    MSG_FILE_NACK,
    MSG_FILE_START,
    MSG_KEY_EVENT,
    MSG_MOUSE_CLICK,
    MSG_MOUSE_MOVE,
    MSG_MOUSE_SCROLL,
    MSG_SWITCH,
    PLATFORM_MAC,
    PLATFORM_WINDOWS,
)

log = logging.getLogger(__name__)


# ── Permission checks ──────────────────────────────────────────────────────────

def _check_mac_accessibility() -> bool:
    """Return True if Accessibility permission is granted on macOS."""
    try:
        from ApplicationServices import AXIsProcessTrusted
        return AXIsProcessTrusted()
    except ImportError:
        try:
            import subprocess
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of every process'],
                capture_output=True, timeout=3,
            )
            return result.returncode == 0
        except Exception:
            return True  # assume OK if we can't check


def _prompt_accessibility() -> None:
    """Show a dialog guiding the user to grant Accessibility permission."""
    try:
        from AppKit import NSWorkspace, NSURL
        import subprocess
        # Open the Accessibility pane in System Settings
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        ])
    except Exception:
        pass

    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        "MouseShare — Permission Required",
        "MouseShare needs Accessibility permission to capture and inject "
        "mouse and keyboard events.\n\n"
        "Please go to:\n"
        "System Settings → Privacy & Security → Accessibility\n\n"
        "Add MouseShare (or your Terminal / Python) to the list, then "
        "restart MouseShare.",
        parent=root,
    )
    root.destroy()


# ── Session — wires all components together ───────────────────────────────────

class Session:
    """
    Owns all components and wires them together.
    One Session per run; create a new one on settings change.
    """

    def __init__(self, config: Config) -> None:
        self.config  = config
        self._loop   = asyncio.get_event_loop()
        self._tasks: list[asyncio.Task] = []

        # Components — initialised in start()
        self._server = None
        self._client = None
        self._capture = None
        self._clip_sync = None
        self._file_receiver = None
        self._drag_detector = None
        self._tray = None

    async def start(self) -> None:
        cfg = self.config

        # TLS cert
        from mouseshare.network.tls import generate_cert
        generate_cert(cfg.cert_dir)

        # ── Choose role ────────────────────────────────────────────────────────
        if cfg.role == "server":
            await self._start_server()
        else:
            await self._start_client()

    async def _start_server(self) -> None:
        cfg = self.config
        from mouseshare.network.server import MouseShareServer
        from mouseshare.input.capture import InputCapture
        from mouseshare.clipboard.sync import ClipboardSync
        from mouseshare.transfer.receiver import FileReceiver
        from mouseshare.input.inject import inject_mouse_move, inject_mouse_click, inject_mouse_scroll, inject_key, move_cursor_to_entry_position
        from mouseshare.network.protocol import (
            decode_mouse_move, decode_mouse_click, decode_mouse_scroll,
            decode_key_event, encode_switch,
        )

        self._server = MouseShareServer(cfg)

        # Clipboard sync
        if cfg.clipboard_sync:
            from mouseshare.clipboard.sync import ClipboardSync
            self._clip_sync = ClipboardSync(self._loop, self._server.send)
            self._server.register(MSG_CLIP_TEXT,  self._clip_sync.handle_text)
            self._server.register(MSG_CLIP_IMAGE, self._clip_sync.handle_image)
            self._clip_sync.start()

        # File receiver (server can also receive files from client)
        if cfg.file_transfer:
            recv_dir = Path(cfg.receive_dir)
            self._file_receiver = FileReceiver(
                receive_dir=recv_dir,
                send_fn=self._server.send,
                on_complete=self._on_file_received,
            )
            self._server.register(MSG_FILE_START, self._file_receiver.handle_start)
            self._server.register(MSG_FILE_CHUNK, self._file_receiver.handle_chunk)
            self._server.register(MSG_FILE_END,   self._file_receiver.handle_end)

        # Input: server receives input back from client (e.g. when client
        # moves mouse back across the edge to return control)
        @self._server.on(MSG_SWITCH)
        async def _on_switch(_msg_type, payload):
            from mouseshare.network.protocol import decode_switch
            direction = decode_switch(payload)
            if self._capture:
                self._capture.set_forwarding(False)
            log.info("Control returned from client (dir=%d)", direction)

        # Input capture — sends events TO the client
        def _on_edge(direction: int):
            """Called (from pynput thread) when mouse hits the trigger edge."""
            frame = encode_switch(direction)
            asyncio.run_coroutine_threadsafe(self._server.send(frame), self._loop)
            log.info("Switched to client (dir=%d)", direction)

        self._capture = InputCapture(
            loop=self._loop,
            send_packet=self._server.send,
            on_edge=_on_edge,
            edge_direction=cfg.other_screen_direction,
        )

        # Drag-drop detector (Mac only)
        if cfg.drag_drop and sys.platform == "darwin":
            from mouseshare.dragdrop.mac_detector import MacDragDropDetector
            self._drag_detector = MacDragDropDetector(
                loop=self._loop,
                edge_direction=cfg.other_screen_direction,
                on_drag_files=self._on_drag_files,
            )
            self._drag_detector.start()

        # Start server + capture
        await self._server.start()
        self._capture.start()
        log.info("Server ready — waiting for client")

        # Block until client connects, then update tray
        await self._server.wait_for_client()
        if self._tray:
            self._tray.set_connected(True, cfg.host)

    async def _start_client(self) -> None:
        cfg = self.config
        from mouseshare.network.client import MouseShareClient
        from mouseshare.input.inject import (
            inject_mouse_move, inject_mouse_click, inject_mouse_scroll,
            inject_key, move_cursor_to_entry_position,
        )
        from mouseshare.network.protocol import (
            decode_mouse_move, decode_mouse_click, decode_mouse_scroll,
            decode_key_event, decode_switch, encode_switch,
        )

        self._client = MouseShareClient(cfg)

        # Input injection handlers
        async def _h_move(_t, p):
            nx, ny = decode_mouse_move(p)
            inject_mouse_move(nx, ny)

        async def _h_click(_t, p):
            btn, pressed = decode_mouse_click(p)
            inject_mouse_click(btn, pressed)

        async def _h_scroll(_t, p):
            dx, dy = decode_mouse_scroll(p)
            inject_mouse_scroll(dx, dy)

        async def _h_key(_t, p):
            code, pressed = decode_key_event(p)
            inject_key(code, pressed)

        # Track whether THIS client currently has control
        _client_active = {"v": False}

        async def _h_switch(_t, p):
            direction = decode_switch(p)
            move_cursor_to_entry_position(direction)
            _client_active["v"] = True
            log.info("Control received from server (dir=%d)", direction)

        self._client.register(MSG_MOUSE_MOVE,   _h_move)
        self._client.register(MSG_MOUSE_CLICK,  _h_click)
        self._client.register(MSG_MOUSE_SCROLL, _h_scroll)
        self._client.register(MSG_KEY_EVENT,    _h_key)
        self._client.register(MSG_SWITCH,       _h_switch)

        # Client-side edge detection: detect when cursor returns to Mac
        from mouseshare.constants import EDGE_THRESHOLD, opposite_edge_direction
        from mouseshare.input.screen import get_screen_size
        import threading as _threading
        import time as _time
        from pynput import mouse as _pmouse

        def _return_edge_watcher():
            """Poll cursor position; when it hits the return edge, send SWITCH back."""
            _ctrl = _pmouse.Controller()
            # The return edge is opposite to the entry direction
            return_dir = opposite_edge_direction(cfg.other_screen_direction)
            while True:
                _time.sleep(0.01)
                if not _client_active["v"]:
                    continue
                try:
                    cx, cy = _ctrl.position
                    w, h   = get_screen_size()
                    hit = False
                    if return_dir == DIR_LEFT   and cx <= EDGE_THRESHOLD:      hit = True
                    if return_dir == DIR_RIGHT  and cx >= w - 1 - EDGE_THRESHOLD: hit = True
                    if return_dir == DIR_TOP    and cy <= EDGE_THRESHOLD:      hit = True
                    if return_dir == DIR_BOTTOM and cy >= h - 1 - EDGE_THRESHOLD: hit = True
                    if hit:
                        _client_active["v"] = False
                        frame = encode_switch(return_dir)
                        asyncio.run_coroutine_threadsafe(
                            self._client.send(frame), self._loop
                        )
                        log.info("Returned control to server")
                except Exception:
                    pass

        _watcher = _threading.Thread(
            target=_return_edge_watcher, daemon=True, name="ms-return-watcher"
        )
        _watcher.start()

        # Clipboard sync
        if cfg.clipboard_sync:
            from mouseshare.clipboard.sync import ClipboardSync
            self._clip_sync = ClipboardSync(self._loop, self._client.send)
            self._client.register(MSG_CLIP_TEXT,  self._clip_sync.handle_text)
            self._client.register(MSG_CLIP_IMAGE, self._clip_sync.handle_image)
            self._clip_sync.start()

        # File receiver
        if cfg.file_transfer:
            from mouseshare.transfer.receiver import FileReceiver
            recv_dir = Path(cfg.receive_dir)
            self._file_receiver = FileReceiver(
                receive_dir=recv_dir,
                send_fn=self._client.send,
                on_complete=self._on_file_received,
            )
            self._client.register(MSG_FILE_START, self._file_receiver.handle_start)
            self._client.register(MSG_FILE_CHUNK, self._file_receiver.handle_chunk)
            self._client.register(MSG_FILE_END,   self._file_receiver.handle_end)
            self._client.register(MSG_FILE_NACK,  self._on_file_nack)

        # Connect (runs reconnect loop indefinitely)
        t = asyncio.create_task(self._client.run(), name="client-loop")
        self._tasks.append(t)
        await self._client.wait_for_connection()
        if self._tray:
            self._tray.set_connected(True, cfg.host)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    async def _on_file_received(self, path: Path) -> None:
        log.info("File received: %s", path)
        if sys.platform == "win32":
            from mouseshare.dragdrop.win_target import notify_file_received
            notify_file_received(path)
        elif sys.platform == "darwin":
            # macOS notification via osascript
            import subprocess
            subprocess.Popen([
                "osascript", "-e",
                f'display notification "Saved to {path.parent}" '
                f'with title "MouseShare" subtitle "{path.name}"'
            ])

    async def _on_file_nack(self, _t, _p) -> None:
        if self._file_receiver:
            # bubble nack to any active sender
            pass
        log.error("File transfer rejected by peer (checksum mismatch)")

    async def _on_drag_files(self, files: list[Path]) -> None:
        """Called when Mac detects a file drag crossing the screen edge."""
        from mouseshare.transfer.sender import FileSender
        from mouseshare.ui.progress import ProgressWindow

        send_fn = self._server.send if self._server else (
            self._client.send if self._client else None
        )
        if not send_fn:
            return

        for file_path in files:
            if not file_path.exists():
                continue
            total = file_path.stat().st_size
            win   = ProgressWindow(f"Sending {file_path.name}", file_path.name, total)
            win.show()

            async def _progress(done, total, _w=win):
                _w.update(done)

            sender = FileSender(send_fn=send_fn, on_progress=_progress)
            ok     = await sender.send(file_path)
            win.close()
            if not ok:
                log.error("Failed to send %s", file_path.name)

    async def stop(self) -> None:
        if self._capture:
            self._capture.stop()
        if self._clip_sync:
            self._clip_sync.stop()
        if self._drag_detector:
            self._drag_detector.stop()
        if self._server:
            await self._server.stop()
        if self._client:
            await self._client.stop()
        for t in self._tasks:
            t.cancel()


# ── Tray + file send helpers (called from tray thread) ───────────────────────

def _pick_and_send_file(session: Session) -> None:
    """Open a file picker and send the chosen file."""
    root = tk.Tk()
    root.withdraw()
    path_str = filedialog.askopenfilename(title="Select file to send")
    root.destroy()
    if not path_str:
        return
    path = Path(path_str)

    loop = asyncio.get_event_loop()

    async def _do_send():
        from mouseshare.transfer.sender import FileSender
        from mouseshare.ui.progress import ProgressWindow

        send_fn = (
            session._server.send if session._server and session._server.is_connected
            else session._client.send if session._client and session._client.is_connected
            else None
        )
        if not send_fn:
            messagebox.showwarning("MouseShare", "Not connected to a peer.")
            return

        total = path.stat().st_size
        win   = ProgressWindow(f"Sending {path.name}", path.name, total)
        win.show()

        async def _progress(done, total, _w=win):
            _w.update(done)

        sender = FileSender(send_fn=send_fn, on_progress=_progress)
        ok     = await sender.send(path)
        win.close()
        if not ok:
            messagebox.showerror("MouseShare", f"Failed to send {path.name}.")

    asyncio.run_coroutine_threadsafe(_do_send(), loop)


# ── Main ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="mouseshare", description="MouseShare")
    p.add_argument("--version",  action="version", version=f"MouseShare {__version__}")
    p.add_argument("--server",   action="store_true", help="Run as server")
    p.add_argument("--client",   action="store_true", help="Run as client")
    p.add_argument("--host",     default=None,  help="Server IP (client mode)")
    p.add_argument("--port",     type=int, default=None)
    p.add_argument("--no-tls",   action="store_true", help="Disable TLS")
    p.add_argument("--debug",    action="store_true", help="Verbose logging")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load / override config
    config = Config.load()
    if args.server:
        config.role = "server"
    if args.client:
        config.role = "client"
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.no_tls:
        config.tls_enabled = False

    # Mac permission check
    if sys.platform == "darwin":
        if not _check_mac_accessibility():
            _prompt_accessibility()
            sys.exit(1)

    # Use uvloop on Mac for lower latency
    if sys.platform == "darwin":
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            log.debug("uvloop active")
        except ImportError:
            pass

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    session = Session(config)

    # Set up tray icon
    from mouseshare.ui.tray import TrayIcon

    def _quit():
        loop.call_soon_threadsafe(loop.stop)

    tray = TrayIcon(
        loop=loop,
        on_send_file=lambda: _pick_and_send_file(session),
        on_open_settings=lambda: _open_settings(config, session, tray),
        on_quit=_quit,
    )
    session._tray = tray

    async def _run():
        await session.start()
        # Keep running until the loop is stopped
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await session.stop()

    # On macOS, pystray must run on the main thread.
    # Run the asyncio loop in a background thread instead.
    def _run_loop():
        try:
            loop.run_until_complete(_run())
        except Exception as exc:
            log.error("Event loop error: %s", exc)
        finally:
            loop.close()
            log.info("MouseShare stopped")
            tray.stop()

    # Pre-cache screen size on the main thread so background threads never
    # need to call tkinter (crashes on macOS 26 Tahoe from non-main threads)
    from mouseshare.input.screen import get_screen_size as _gss
    _gss()

    loop_thread = threading.Thread(target=_run_loop, daemon=True, name="ms-asyncio")
    loop_thread.start()

    # Run tray on main thread (required on macOS)
    try:
        tray.start()   # blocks until quit
    except (KeyboardInterrupt, SystemExit):
        _quit()

    loop_thread.join(timeout=3)


def _open_settings(config: Config, session: Session, tray) -> None:
    from mouseshare.ui.settings import open_settings

    def _on_save(new_config: Config):
        # Update capture edge direction live if server is running
        if session._capture:
            session._capture.set_edge_direction(new_config.other_screen_direction)
        if session._drag_detector:
            session._drag_detector.set_edge_direction(new_config.other_screen_direction)

    open_settings(config, on_save=_on_save)


if __name__ == "__main__":
    main()

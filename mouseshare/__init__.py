"""MouseShare — open-source mouse/keyboard/clipboard/file sharing across Mac and Windows."""

__version__ = "0.1.0"
__author__ = "MouseShare Contributors"
__license__ = "MIT"

import sys as _sys

if _sys.platform == "darwin":
    # pynput 1.7.x imports several CoreFoundation symbols from the Quartz
    # module.  In pyobjc >= 10.0 those symbols are no longer re-exported by
    # Quartz; they live in CoreFoundation instead.  Inject them before pynput
    # is imported so its darwin backend can find them.
    def _patch_quartz_for_pynput() -> None:
        _CF_SYMBOLS = [
            "CFMachPortCreateRunLoopSource",
            "CFRunLoopAddSource",
            "CFRunLoopRun",
            "CFRunLoopStop",
            "CFRunLoopGetCurrent",
            "CFRunLoopSourceCreate",
            "CFRunLoopSourceInvalidate",
            "kCFRunLoopDefaultMode",
            "CFMachPortInvalidate",
        ]
        try:
            import Quartz as _Q
            import CoreFoundation as _CF
        except ImportError:
            return
        for _sym in _CF_SYMBOLS:
            if not hasattr(_Q, _sym):
                try:
                    setattr(_Q, _sym, getattr(_CF, _sym))
                except AttributeError:
                    pass

    _patch_quartz_for_pynput()

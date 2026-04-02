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
    #
    # NOTE: pyobjc's lazy importer raises KeyError (not AttributeError) for
    # missing symbols, so we must catch both when probing / fetching.
    def _patch_quartz_for_pynput() -> None:
        _CF_SYMBOLS = [
            "CFMachPortCreateRunLoopSource",
            "CFMachPortInvalidate",
            "CFRunLoopAddSource",
            "CFRunLoopRun",
            "CFRunLoopStop",
            "CFRunLoopGetCurrent",
            "CFRunLoopSourceCreate",
            "CFRunLoopSourceInvalidate",
            "kCFRunLoopDefaultMode",
        ]
        try:
            import Quartz as _Q
        except ImportError:
            return
        try:
            import CoreFoundation as _CF
        except ImportError:
            return
        for _sym in _CF_SYMBOLS:
            # Check whether it already exists in Quartz
            try:
                getattr(_Q, _sym)
                continue  # already available — nothing to do
            except (AttributeError, KeyError):
                pass
            # Fetch from CoreFoundation and inject into Quartz
            try:
                _val = getattr(_CF, _sym)
                setattr(_Q, _sym, _val)
            except Exception:
                pass  # best-effort; pynput will report a clearer error if missing

    _patch_quartz_for_pynput()

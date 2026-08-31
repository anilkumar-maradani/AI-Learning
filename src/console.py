"""
console.py — Make stdout/stderr UTF-8 on every platform.

Windows consoles default to a legacy code page (cp1252), so printing box
characters or emoji raises UnicodeEncodeError. Calling ``enable_utf8()`` at the
top of each entry point makes output behave the same as on macOS/Linux.
"""

import sys


def enable_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, AttributeError):
                pass

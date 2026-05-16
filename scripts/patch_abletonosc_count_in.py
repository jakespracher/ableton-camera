#!/usr/bin/env python3
"""Add is_counting_in to the installed AbletonOSC song handler (macOS User Library)."""

from __future__ import annotations

import sys
from pathlib import Path

SONG_PY = (
    Path.home()
    / "Music/Ableton/User Library/Remote Scripts/AbletonOSC/abletonosc/song.py"
)
NEEDLE = '"session_record_status"'
INSERT = '"is_counting_in",\n            "session_record_status"'


def main() -> int:
    if not SONG_PY.is_file():
        print(f"Not found: {SONG_PY}", file=sys.stderr)
        return 1
    text = SONG_PY.read_text(encoding="utf-8")
    if '"is_counting_in"' in text:
        print("Already patched.")
        return 0
    if NEEDLE not in text:
        print("Unexpected song.py format; patch manually.", file=sys.stderr)
        return 1
    SONG_PY.write_text(text.replace(NEEDLE, INSERT, 1), encoding="utf-8")
    print(f"Patched {SONG_PY}")
    print("Quit and reopen Ableton Live for the change to load.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

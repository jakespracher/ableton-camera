#!/usr/bin/env python3
"""Send /live/test to AbletonOSC; Live should show a status-bar confirmation."""

from __future__ import annotations

import sys

from pythonosc.udp_client import SimpleUDPClient


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11000
    client = SimpleUDPClient(host, port)
    client.send_message("/live/test", [])
    print(f"Sent /live/test → {host}:{port}")
    print("If AbletonOSC is enabled in Live, check the status bar for a confirmation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

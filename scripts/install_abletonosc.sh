#!/usr/bin/env bash
# Install or update AbletonOSC into the Ableton User Library Remote Scripts folder (macOS).
set -euo pipefail

REMOTE="${HOME}/Music/Ableton/User Library/Remote Scripts"
WORK="${TMPDIR:-/tmp}/abletonosc-install-$$"
ZIP="${WORK}/AbletonOSC.zip"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script targets macOS. On Windows, copy AbletonOSC to:" >&2
  echo "  %USERPROFILE%\\Documents\\Ableton\\User Library\\Remote Scripts" >&2
  exit 1
fi

mkdir -p "$REMOTE" "$WORK"
trap 'rm -rf "$WORK"' EXIT

echo "Downloading AbletonOSC..."
curl -fsSL -o "$ZIP" "https://github.com/ideoforms/AbletonOSC/archive/refs/heads/master.zip"
unzip -q "$ZIP" -d "$WORK"

if [[ -d "${REMOTE}/AbletonOSC" ]]; then
  echo "Replacing existing ${REMOTE}/AbletonOSC"
  rm -rf "${REMOTE}/AbletonOSC"
fi

mv "${WORK}/AbletonOSC-master" "${REMOTE}/AbletonOSC"
echo "Installed to: ${REMOTE}/AbletonOSC"
echo ""
echo "Next steps (manual):"
echo "  1. Quit and reopen Ableton Live"
echo "  2. Preferences → Link / Tempo / MIDI → Control Surface → AbletonOSC"
echo "  3. Confirm status: AbletonOSC: Listening for OSC on port 11000"
echo "  4. Test: python scripts/smoke_abletonosc.py"

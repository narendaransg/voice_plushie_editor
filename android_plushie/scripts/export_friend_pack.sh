#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APK_SRC="$ROOT_DIR/app/build/outputs/apk/debug/app-debug.apk"
RELEASE_DIR="$HOME/voice_plushie_editor/release"
PACK_DIR="$RELEASE_DIR/friend-pack"

if [[ ! -f "$APK_SRC" ]]; then
  echo "APK not found at $APK_SRC. Run ./gradlew assembleDebug first." >&2
  exit 1
fi

mkdir -p "$PACK_DIR"
cp "$APK_SRC" "$RELEASE_DIR/SaveRoomPlushie-debug.apk"
cp "$APK_SRC" "$PACK_DIR/SaveRoomPlushie-debug.apk"

cat <<'TXT' > "$PACK_DIR/FRIEND_INSTALL_GUIDE.txt"
Save Room Plushie — Friend Install Guide
======================================
1. Copy SaveRoomPlushie-debug.apk to your Android phone.
2. Tap the APK file and allow "Install unknown apps" if prompted.
3. Open Save Room Plushie:
   - Type any answer (or tap Open Save Room Door) at the entry checkpoint.
   - Grant "Display over other apps" if you want the floating Leon overlay outside the app.
   - Grant "Usage access" in Settings if you want 10s warning + auto-exit during focus blocks.
TXT

cat <<'JSON' > "$PACK_DIR/sample-poster-feed.json"
{
  "posters": [
    {
      "poster_id": "friend-welcome-01",
      "admin_id": "narendaransg",
      "title": "SAVE ROOM BRIEFING",
      "message": "Welcome to Save Room Plushie! Check the Field & Comms tab for the tutorial and feedback corner.",
      "badge_tag": "CREATOR DISPATCH"
    }
  ]
}
JSON

echo "Exported friend pack to: $PACK_DIR"
ls -lh "$PACK_DIR"

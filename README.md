# voice_plushie_editor

Repository for **Save Room Plushie** (`android_plushie`), a Resident Evil Save Room–inspired Android focus, routine, and companion app built with Kotlin and Jetpack Compose, alongside theme/config assets, scripts, and archived experiments.

## Features (`android_plushie` — `com.raccoon.plushie`)

* **Four-Tab Save Room Interface:** Navigate across **Save Room**, **Care & Shield**, **Attache Case**, and **Field & Comms** with high-contrast low-light (`NightOps`) readability and optional CRT scanlines.
* **Companion & Floating Overlay:** Includes a roaming axolotl (`#AX-01`) companion and an optional floating Leon overlay (`LeonOverlayService`) when **Display over other apps** is granted.
* **Focus Containment (`ContainmentService`):** Monitors foreground usage (when **Usage access** is granted) to trigger a 10-second warning and return to Home during active focus blocks.
* **Audio & TTS (`SaveRoomSoundEffects`):** Uses `SoundPool`, `MediaPlayer`, and `TextToSpeech` (`com.google.android.tts`) for cues and status feedback. Final voiceover/audio routing polish is planned for future updates.
* **Signed Admin Poster Feed (`RemotePosterRepository`):** Fetches HTTPS poster dispatches filtered by `admin_id` with optional SHA-256 verification over `poster_id|title|message|signing_key`.
* **Friend Pack Exporter (`android_plushie/scripts/export_friend_pack.sh`):** Bundles `SaveRoomPlushie-debug.apk`, `FRIEND_INSTALL_GUIDE.txt`, and `sample-poster-feed.json` into `~/voice_plushie_editor/release/friend-pack/`.

## Repository Structure

* `android_plushie/` — Active Kotlin + Jetpack Compose Android project, raw/drawable resources, and scripts.
* `themes/` — Theme assets and configurations, such as `re_leon`.
* `config/` — Project configuration files.
* `scripts/` — Top-level repository helper scripts.
* `models/` — Local model/reference files, excluded from Git.
* `archive/` — Archived prototypes and earlier experiments.

## Build, Friend Pack & ADB Workflow (WSL2)

Run the following commands:

```bash
cd ~/voice_plushie_editor/android_plushie
./gradlew assembleDebug
./scripts/export_friend_pack.sh
adb install -r ~/voice_plushie_editor/release/friend-pack/SaveRoomPlushie-debug.apk
adb shell am start -n com.raccoon.plushie/.MainActivity
```

The friend pack is exported to:

`~/voice_plushie_editor/release/friend-pack/`

Share `SaveRoomPlushie-debug.apk` and `FRIEND_INSTALL_GUIDE.txt` from that directory with testers.

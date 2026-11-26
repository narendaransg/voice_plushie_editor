# Future Session Handoff
## Save Room Plushie

Repository: ~/voice_plushie_editor
Branch: main / master
Package: com.raccoon.plushie

## Current Application

Location:
android_plushie/app/src/main/java/com/raccoon/plushie/

Features:
- Four-tab Jetpack Compose interface.
- Save Room.
- Care & Shield.
- Attache Case.
- Field & Comms.
- Roaming axolotl companion #AX-01.
- Floating LeonOverlayService.
- ContainmentService with 10-second warning.
- RemotePosterRepository.
- SaveRoomSoundEffects.

## Audio

SaveRoomSoundEffects.kt and app/src/main/res/raw/

Existing effects:
- sfx_typewriter_save.wav
- sfx_herb_chime.wav
- sfx_shield_alert.wav

TextToSpeech uses com.google.android.tts.

Remaining work:
- Verify sfx_re_intro.wav playback.
- Verify TTS playback on target devices.
- Polish character voiceovers and sound effects.
- Test audio behavior on multiple Android devices.

## Friend Pack

Script:
android_plushie/scripts/export_friend_pack.sh

Output:
release/friend-pack/

## Additional Tasks

1. Add adaptive launcher icon XML.
2. Add GitHub Actions Android build workflow.
3. Test containment and overlay services.
4. Verify poster signature validation.
5. Verify friend-pack installation.

## Admin Commands

plushie build
plushie update
plushie post
plushie logs
plushie handoff
plushie push

Keep release/, assets/, .gradle/, and build directories
out of Git commits.

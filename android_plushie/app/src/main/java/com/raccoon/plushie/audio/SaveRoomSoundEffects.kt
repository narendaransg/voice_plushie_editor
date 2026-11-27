package com.raccoon.plushie.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.SoundPool
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.util.Log
import java.util.Locale

class SaveRoomSoundEffects(private val context: Context) {

    private val mainHandler = Handler(Looper.getMainLooper())
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var mediaPlayer: MediaPlayer? = null

    private val attrs = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_MEDIA)
        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
        .build()

    private val soundPool: SoundPool = SoundPool.Builder()
        .setMaxStreams(6)
        .setAudioAttributes(attrs)
        .build().apply {
            setOnLoadCompleteListener { _, sampleId, status ->
                Log.i("SaveRoomAudio", "SoundPool load sampleId=$sampleId status=$status")
            }
        }

    private val loadedIds = mutableMapOf<String, Int>()

    init {
        listOf(
            "sfx_typewriter_save",
            "sfx_herb_chime",
            "sfx_shield_alert",
            "sfx_level_up",
            "sfx_tree_grow",
            "sfx_ui_tap"
        ).forEach { loadRawSound(it) }

        tts = TextToSpeech(context.applicationContext) { status ->
            ttsReady = (status == TextToSpeech.SUCCESS)
            Log.i("SaveRoomAudio", "TTS init status=$status ready=$ttsReady")
            if (ttsReady) {
                tts?.language = Locale.US
            }
        }
    }

    private fun loadRawSound(name: String) {
        val resId = context.resources.getIdentifier(name, "raw", context.packageName)
        if (resId != 0) {
            val id = soundPool.load(context, resId, 1)
            loadedIds[name] = id
        } else {
            Log.w("SaveRoomAudio", "Missing raw resource: $name")
        }
    }

    fun playUiTap() {
        if (!playFromPool("sfx_ui_tap")) {
            playRawFallback("sfx_ui_tap")
        }
    }

    fun playTypewriterSave() {
        if (!playFromPool("sfx_typewriter_save")) {
            playRawFallback("sfx_typewriter_save")
        }
    }

    fun playHerbChime() {
        if (!playFromPool("sfx_herb_chime")) {
            playRawFallback("sfx_herb_chime")
        }
    }

    fun playShieldAlert() {
        if (!playFromPool("sfx_shield_alert")) {
            playRawFallback("sfx_shield_alert")
        }
    }

    fun playLevelUp() {
        if (!playFromPool("sfx_level_up")) {
            playRawFallback("sfx_level_up")
        }
    }

    fun playTreeGrow() {
        if (!playFromPool("sfx_tree_grow")) {
            playRawFallback("sfx_tree_grow")
        }
    }

    fun playOpeningPunchline(enableVoice: Boolean = false) {
        Log.i("SaveRoomAudio", "playOpeningPunchline enableVoice=$enableVoice")
        if (!playRawFallback("sfx_re_intro")) {
            playHerbChime()
        }
        if (enableVoice && ttsReady) {
            val code = tts?.speak(
                "Save room secured. Stay sharp.",
                TextToSpeech.QUEUE_FLUSH,
                null,
                "save_room_intro"
            )
            Log.i("SaveRoomAudio", "TTS speak code=$code")
        }
    }

    private fun playFromPool(key: String): Boolean {
        val sid = loadedIds[key] ?: return false
        return try {
            val streamId = soundPool.play(sid, 0.92f, 0.92f, 1, 0, 1.0f)
            Log.i("SaveRoomAudio", "SoundPool play $key -> streamId=$streamId")
            streamId != 0
        } catch (e: Exception) {
            Log.w("SaveRoomAudio", "SoundPool error for $key: ${e.message}")
            false
        }
    }

    private fun playRawFallback(name: String): Boolean {
        val rawId = context.resources.getIdentifier(name, "raw", context.packageName)
        if (rawId == 0) return false
        return try {
            mediaPlayer?.release()
            val mp = MediaPlayer.create(context, rawId) ?: return false
            mediaPlayer = mp
            mp.setOnCompletionListener {
                it.release()
                if (mediaPlayer === it) mediaPlayer = null
            }
            mp.setOnErrorListener { player, what, extra ->
                Log.w("SaveRoomAudio", "MediaPlayer error name=$name what=$what extra=$extra")
                player.release()
                if (mediaPlayer === player) mediaPlayer = null
                true
            }
            mainHandler.post {
                try {
                    mp.start()
                    Log.i("SaveRoomAudio", "MediaPlayer started $name")
                } catch (e: Exception) {
                    Log.w("SaveRoomAudio", "MediaPlayer start failed $name: ${e.message}")
                }
            }
            true
        } catch (e: Exception) {
            Log.w("SaveRoomAudio", "playRawFallback failed $name: ${e.message}")
            false
        }
    }

    fun release() {
        mainHandler.removeCallbacksAndMessages(null)
        mediaPlayer?.release()
        mediaPlayer = null
        soundPool.release()
        tts?.stop()
        tts?.shutdown()
        tts = null
    }
}

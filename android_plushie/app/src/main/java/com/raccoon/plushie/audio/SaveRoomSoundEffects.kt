package com.raccoon.plushie.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.media.MediaPlayer
import android.media.SoundPool
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.util.Log
import java.util.Locale
import kotlin.math.PI
import kotlin.math.sin

class SaveRoomSoundEffects(private val context: Context) {
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var pendingLine: String? = null
    private var mediaPlayer: MediaPlayer? = null
    private val mainHandler = Handler(Looper.getMainLooper())

    private val audioAttrs = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_MEDIA)
        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
        .build()

    private val soundPool: SoundPool = SoundPool.Builder()
        .setMaxStreams(4)
        .setAudioAttributes(audioAttrs)
        .build()

    private val soundIds = mutableMapOf<String, Int>()
    private val loadedIds = mutableSetOf<Int>()

    init {
        soundPool.setOnLoadCompleteListener { _, sampleId, status ->
            Log.i("SaveRoomAudio", "SoundPool load sampleId=$sampleId status=$status")
            if (status == 0) {
                loadedIds.add(sampleId)
            }
        }
        loadRawSound("sfx_typewriter_save")
        loadRawSound("sfx_herb_chime")
        loadRawSound("sfx_shield_alert")

        tts = TextToSpeech(context.applicationContext) { status ->
            Log.i("SaveRoomAudio", "TTS init status=$status")
            if (status == TextToSpeech.SUCCESS) {
                tts?.language = Locale.US
                tts?.setPitch(0.88f)
                tts?.setSpeechRate(0.98f)
                ttsReady = true
                pendingLine?.let { line ->
                    pendingLine = null
                    speakPunchline(line)
                }
            }
        }
    }

    private fun loadRawSound(name: String) {
        val resId = context.resources.getIdentifier(name, "raw", context.packageName)
        Log.i("SaveRoomAudio", "Res lookup $name -> resId=$resId")
        if (resId != 0) {
            try {
                soundIds[name] = soundPool.load(context, resId, 1)
            } catch (e: Exception) {
                Log.i("SaveRoomAudio", "SoundPool load failed for $name: ${e.message}")
            }
        }
    }

    fun playOpeningPunchline() {
        val rawId = context.resources.getIdentifier("sfx_re_intro", "raw", context.packageName)
        Log.i("SaveRoomAudio", "playOpeningPunchline rawId=$rawId")
        if (rawId != 0 && playRawIntroSync(rawId)) return
        speakPunchline("Save room secured. Ink ribbon ready, stay sharp.")
        playPcmChime(523.25, 659.25)
    }

    fun playTypewriterSave() {
        Log.i("SaveRoomAudio", "playTypewriterSave")
        if (!playFromPool("sfx_typewriter_save")) {
            playPcmChime(440.0, 880.0)
        }
    }

    fun playHerbOrShinyChime() {
        Log.i("SaveRoomAudio", "playHerbOrShinyChime")
        if (!playFromPool("sfx_herb_chime")) {
            playPcmChime(587.33, 880.0)
        }
    }

    fun playShieldAlert() {
        Log.i("SaveRoomAudio", "playShieldAlert")
        if (!playFromPool("sfx_shield_alert")) {
            playPcmChime(311.13, 233.08)
        }
    }

    private fun playFromPool(key: String): Boolean {
        val sid = soundIds[key] ?: return false
        if (sid !in loadedIds) {
            Log.i("SaveRoomAudio", "SoundPool sample not loaded yet: $key ($sid)")
            return false
        }
        return try {
            val streamId = soundPool.play(sid, 1.0f, 1.0f, 1, 0, 1.0f)
            Log.i("SaveRoomAudio", "SoundPool play $key -> streamId=$streamId")
            streamId != 0
        } catch (e: Exception) {
            Log.i("SaveRoomAudio", "SoundPool play error $key: ${e.message}")
            false
        }
    }

    private fun playRawIntroSync(resId: Int): Boolean {
        return try {
            mediaPlayer?.release()
            val afd = context.resources.openRawResourceFd(resId) ?: return false
            val mp = MediaPlayer().apply {
                setAudioAttributes(audioAttrs)
                setDataSource(afd.fileDescriptor, afd.startOffset, afd.length)
                afd.close()
                prepare()
                setOnCompletionListener { player ->
                    player.release()
                    if (mediaPlayer === player) mediaPlayer = null
                }
                start()
            }
            mediaPlayer = mp
            Log.i("SaveRoomAudio", "MediaPlayer started sfx_re_intro")
            true
        } catch (e: Exception) {
            Log.i("SaveRoomAudio", "MediaPlayer error: ${e.message}")
            false
        }
    }

    private fun speakPunchline(text: String) {
        if (ttsReady) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "re_intro_line")
            } else {
                @Suppress("DEPRECATION")
                tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null)
            }
        } else {
            pendingLine = text
        }
    }

    private fun playPcmChime(freq1: Double, freq2: Double) {
        Thread {
            try {
                val sampleRate = 22050
                val durSamples = (sampleRate * 0.16).toInt()
                val totalSamples = durSamples * 2
                val pcm = ShortArray(totalSamples)
                val freqs = doubleArrayOf(freq1, freq2)
                for (segment in 0..1) {
                    val f = freqs[segment]
                    for (i in 0 until durSamples) {
                        val env = sin(PI * i / (durSamples - 1).coerceAtLeast(1))
                        val sample = sin(2.0 * PI * f * i / sampleRate) * 0.45 * env
                        pcm[segment * durSamples + i] = (sample * Short.MAX_VALUE).toInt().toShort()
                    }
                }
                val minBuf = AudioTrack.getMinBufferSize(
                    sampleRate,
                    AudioFormat.CHANNEL_OUT_MONO,
                    AudioFormat.ENCODING_PCM_16BIT
                ).coerceAtLeast(totalSamples * 2)

                val track = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    AudioTrack.Builder()
                        .setAudioAttributes(audioAttrs)
                        .setAudioFormat(
                            AudioFormat.Builder()
                                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                                .setSampleRate(sampleRate)
                                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                                .build()
                        )
                        .setBufferSizeInBytes(minBuf)
                        .setTransferMode(AudioTrack.MODE_STREAM)
                        .build()
                } else {
                    @Suppress("DEPRECATION")
                    AudioTrack(
                        AudioManager.STREAM_MUSIC,
                        sampleRate,
                        AudioFormat.CHANNEL_OUT_MONO,
                        AudioFormat.ENCODING_PCM_16BIT,
                        minBuf,
                        AudioTrack.MODE_STREAM
                    )
                }

                track.play()
                track.write(pcm, 0, pcm.size)
                Thread.sleep(360L)
                track.stop()
                track.release()
                Log.i("SaveRoomAudio", "AudioTrack PCM chime played ($freq1 -> $freq2)")
            } catch (e: Exception) {
                Log.i("SaveRoomAudio", "AudioTrack error: ${e.message}")
            }
        }.start()
    }

    fun release() {
        mainHandler.removeCallbacksAndMessages(null)
        try {
            mediaPlayer?.release()
        } catch (_: Exception) {
        }
        mediaPlayer = null
        try {
            soundPool.release()
        } catch (_: Exception) {
        }
        try {
            tts?.stop()
            tts?.shutdown()
        } catch (_: Exception) {
        }
        tts = null
    }
}

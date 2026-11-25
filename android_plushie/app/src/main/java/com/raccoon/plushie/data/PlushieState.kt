package com.raccoon.plushie.data

import android.content.Context
import androidx.compose.runtime.Immutable

@Immutable
data class StashEntry(
    val id: String,
    val title: String,
    val category: String,
    val shiny: Boolean = false
)

@Immutable
data class PlushieUiState(
    val pomodoroMinutes: Int = 25,
    val remainingSeconds: Int = 25 * 60,
    val isTimerRunning: Boolean = false,
    val stealthFaceDown: Boolean = false,
    val lowLightNightOps: Boolean = false,
    val tiltX: Float = 0f,
    val tiltY: Float = 0f,
    val completedSessions: Int = 0,
    val zeroDistractionSessions: Int = 0,
    val instagramMinutesToday: Int = 0,
    val firstAidSpraysLeft: Int = 2,
    val herbPoints: Int = 15,
    val shinyAxolotlUnlocked: Boolean = false,
    val shinyCount: Int = 1,
    val crtScanlinesEnabled: Boolean = false,
    val terminalThemeActive: Boolean = false,
    val merchantAvailable: Boolean = false,
    val usageAccessGranted: Boolean = false,
    val overlayPermissionGranted: Boolean = false,
    val termuxInstalled: Boolean = false,
    val bannerMessage: String = "Save Room ready. Typewriter ink ribbon primed.",
    val easterEggToast: String? = null,
    val stashItems: List<StashEntry> = listOf(
        StashEntry("1", "GATE ECE Signals — Laplace notes", "STUDY", shiny = false),
        StashEntry("2", "Specimen #AX-01 — Shiny Blue Axolotl", "AXOLOTL", shiny = true),
        StashEntry("3", "Redstone Comparator Clock (64-tick)", "MINECRAFT", shiny = false),
        StashEntry("4", "Setup/Hold Slack +0.42ns Report", "VLSI", shiny = true)
    )
) {
    val herbStatus: String
        get() = when {
            instagramMinutesToday >= 45 -> "DANGER (Red Herb)"
            instagramMinutesToday >= 20 -> "CAUTION (Yellow+Green)"
            else -> "FINE (Green Herb)"
        }
}

class PlushiePrefs(context: Context) {
    private val prefs = context.getSharedPreferences("raccoon_plushie_prefs", Context.MODE_PRIVATE)

    fun loadInitial(): PlushieUiState {
        val focusMins = prefs.getInt("pomodoro_mins", 25).coerceIn(5, 90)
        return PlushieUiState(
            pomodoroMinutes = focusMins,
            remainingSeconds = focusMins * 60,
            completedSessions = prefs.getInt("completed_sessions", 0),
            zeroDistractionSessions = prefs.getInt("zero_distraction_sessions", 0),
            instagramMinutesToday = prefs.getInt("ig_mins_today", 0),
            firstAidSpraysLeft = prefs.getInt("sprays_left", 2),
            herbPoints = prefs.getInt("herb_points", 15),
            shinyAxolotlUnlocked = prefs.getBoolean("shiny_axolotl", false),
            shinyCount = prefs.getInt("shiny_count", 1),
            crtScanlinesEnabled = prefs.getBoolean("crt_enabled", false),
            terminalThemeActive = prefs.getBoolean("term_theme", false)
        )
    }

    fun save(state: PlushieUiState) {
        prefs.edit()
            .putInt("pomodoro_mins", state.pomodoroMinutes)
            .putInt("completed_sessions", state.completedSessions)
            .putInt("zero_distraction_sessions", state.zeroDistractionSessions)
            .putInt("ig_mins_today", state.instagramMinutesToday)
            .putInt("sprays_left", state.firstAidSpraysLeft)
            .putInt("herb_points", state.herbPoints)
            .putBoolean("shiny_axolotl", state.shinyAxolotlUnlocked)
            .putInt("shiny_count", state.shinyCount)
            .putBoolean("crt_enabled", state.crtScanlinesEnabled)
            .putBoolean("term_theme", state.terminalThemeActive)
            .apply()
    }
}

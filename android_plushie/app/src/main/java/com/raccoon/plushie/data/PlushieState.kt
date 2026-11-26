package com.raccoon.plushie.data

import android.content.Context
import androidx.compose.runtime.Immutable
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate

@Immutable
data class TodoTask(
    val id: String,
    val title: String,
    val dueEpochMs: Long? = null,
    val done: Boolean = false,
    val shiny: Boolean = false,
    val calendarSynced: Boolean = false,
    val alarmSet: Boolean = false
)

@Immutable
data class PlushieUiState(
    val timerModeBreak: Boolean = false,
    val pomodoroMinutes: Int = 25,
    val breakMinutes: Int = 5,
    val remainingSeconds: Int = 25 * 60,
    val targetEndTimeMs: Long = 0L,
    val isTimerRunning: Boolean = false,
    val sessionDistractionHits: Int = 0,
    val streakDays: Int = 1,
    val lastActiveEpochDay: Long = 0L,
    val inkRibbonGraceTokens: Int = 1,
    val unlockedSpecimenTier: Int = 1,
    val leonOverlayEnabled: Boolean = false,
    val axolotlRoamingEnabled: Boolean = true,
    val axolotlHunger: Int = 78,
    val axolotlAffection: Int = 72,
    val petCountToday: Int = 0,
    val careAlertsEnabled: Boolean = true,
    val autoSetAlarmOnSchedule: Boolean = true,
    val autoSyncCalendarOnSchedule: Boolean = true,
    val signedInGmail: String? = null,
    val stealthFaceDown: Boolean = false,
    val lowLightNightOps: Boolean = false,
    val tiltX: Float = 0f,
    val tiltY: Float = 0f,
    val completedSessions: Int = 0,
    val zeroDistractionSessions: Int = 0,
    val instagramMinutesToday: Int = 0,
    val firstAidSpraysLeft: Int = 2,
    val herbPoints: Int = 30,
    val shinyAxolotlUnlocked: Boolean = false,
    val shinyCount: Int = 1,
    val crtScanlinesEnabled: Boolean = false,
    val terminalThemeActive: Boolean = false,
    val merchantAvailable: Boolean = false,
    val usageAccessGranted: Boolean = false,
    val overlayPermissionGranted: Boolean = false,
    val termuxInstalled: Boolean = false,
    val blockedPackages: Set<String> = setOf("com.instagram.android"),
    val bannerMessage: String = "Save Room ready. Typewriter ink ribbon primed.",
    val easterEggToast: String? = null,
    val todos: List<TodoTask> = listOf(
        TodoTask("t1", "GATE ECE Signals — Laplace & Fourier drill", dueEpochMs = null, done = false, shiny = false),
        TodoTask("t2", "Specimen #AX-01 — Pet & feed Shiny Blue Axolotl", dueEpochMs = null, done = false, shiny = true),
        TodoTask("t3", "AXI4 iDMA RTL & STA slack check", dueEpochMs = null, done = false, shiny = true)
    )
) {
    val activeBlockMinutes: Int
        get() = if (timerModeBreak) breakMinutes else pomodoroMinutes

    val herbStatus: String
        get() = when {
            instagramMinutesToday >= 45 -> "DANGER (Red Herb)"
            instagramMinutesToday >= 20 -> "CAUTION (Yellow+Green)"
            else -> "FINE (Green Herb)"
        }

    val rankTitle: String
        get() = when {
            streakDays >= 14 -> "Umbrella Specimen Master"
            streakDays >= 7 -> "S.T.A.R.S. Tactical Specialist"
            streakDays >= 3 -> "Raccoon City Survivor"
            else -> "Save Room Rookie"
        }

    val specimenVariantLabel: String
        get() = when {
            streakDays >= 14 || shinyCount >= 12 -> "Specimen #AX-03 Prism Axolotl"
            streakDays >= 7 || shinyCount >= 6 -> "Specimen #AX-02 Astral Gold Axolotl"
            else -> "Specimen #AX-01 Shiny Blue Axolotl"
        }
}

class PlushiePrefs(context: Context) {
    private val prefs = context.getSharedPreferences("raccoon_plushie_prefs", Context.MODE_PRIVATE)

    fun loadInitial(): PlushieUiState {
        val isBreak = prefs.getBoolean("timer_mode_break", false)
        val focusMins = prefs.getInt("pomodoro_mins", 25).coerceIn(5, 90)
        val breakMins = prefs.getInt("break_mins", 5).coerceIn(1, 30)
        val defaultSecs = (if (isBreak) breakMins else focusMins) * 60

        val wasRunning = prefs.getBoolean("timer_running", false)
        val savedTargetMs = prefs.getLong("timer_target_ms", 0L)
        val savedRemaining = prefs.getInt("timer_remaining_sec", defaultSecs)

        val now = System.currentTimeMillis()
        val (computedSec, stillRunning, newTargetMs) = if (wasRunning && savedTargetMs > 0L) {
            val left = ((savedTargetMs - now) / 1000L).toInt()
            if (left > 0) Triple(left, true, savedTargetMs) else Triple(defaultSecs, false, 0L)
        } else {
            Triple(savedRemaining.coerceIn(1, defaultSecs.coerceAtLeast(60)), false, 0L)
        }

        val todayEpoch = LocalDate.now().toEpochDay()
        var streak = prefs.getInt("streak_days", 1).coerceAtLeast(1)
        val lastDay = prefs.getLong("last_active_day", todayEpoch)
        var grace = prefs.getInt("ink_grace_tokens", 1).coerceAtLeast(0)

        val gap = todayEpoch - lastDay
        if (gap == 2L && grace > 0) {
            grace -= 1
        } else if (gap > 1L) {
            streak = 1
        }

        val blocked = prefs.getStringSet("blocked_packages", setOf("com.instagram.android"))
            ?.filter { it.isNotBlank() }?.toSet()
            ?: setOf("com.instagram.android")

        val parsedTodos = parseTodos(prefs.getString("todos_json", null))

        return PlushieUiState(
            timerModeBreak = isBreak,
            pomodoroMinutes = focusMins,
            breakMinutes = breakMins,
            remainingSeconds = computedSec,
            targetEndTimeMs = newTargetMs,
            isTimerRunning = stillRunning,
            sessionDistractionHits = prefs.getInt("session_hits", 0),
            streakDays = streak,
            lastActiveEpochDay = lastDay,
            inkRibbonGraceTokens = grace,
            unlockedSpecimenTier = prefs.getInt("specimen_tier", 1),
            leonOverlayEnabled = prefs.getBoolean("leon_overlay", false),
            axolotlRoamingEnabled = prefs.getBoolean("axo_roam", true),
            axolotlHunger = prefs.getInt("axo_hunger", 78).coerceIn(0, 100),
            axolotlAffection = prefs.getInt("axo_affection", 72).coerceIn(0, 100),
            petCountToday = prefs.getInt("pet_count", 0),
            careAlertsEnabled = prefs.getBoolean("care_alerts", true),
            autoSetAlarmOnSchedule = prefs.getBoolean("auto_alarm", true),
            autoSyncCalendarOnSchedule = prefs.getBoolean("auto_calendar", true),
            signedInGmail = prefs.getString("signed_gmail", null),
            completedSessions = prefs.getInt("completed_sessions", 0),
            zeroDistractionSessions = prefs.getInt("zero_distraction_sessions", 0),
            instagramMinutesToday = prefs.getInt("ig_mins_today", 0),
            firstAidSpraysLeft = prefs.getInt("sprays_left", 2),
            herbPoints = prefs.getInt("herb_points", 30),
            shinyAxolotlUnlocked = prefs.getBoolean("shiny_axolotl", false),
            shinyCount = prefs.getInt("shiny_count", 1),
            crtScanlinesEnabled = prefs.getBoolean("crt_enabled", false),
            terminalThemeActive = prefs.getBoolean("term_theme", false),
            blockedPackages = blocked,
            todos = parsedTodos ?: PlushieUiState().todos
        )
    }

    fun save(state: PlushieUiState) {
        prefs.edit()
            .putBoolean("timer_mode_break", state.timerModeBreak)
            .putInt("pomodoro_mins", state.pomodoroMinutes)
            .putInt("break_mins", state.breakMinutes)
            .putInt("timer_remaining_sec", state.remainingSeconds)
            .putLong("timer_target_ms", state.targetEndTimeMs)
            .putBoolean("timer_running", state.isTimerRunning)
            .putInt("session_hits", state.sessionDistractionHits)
            .putInt("streak_days", state.streakDays)
            .putLong("last_active_day", state.lastActiveEpochDay)
            .putInt("ink_grace_tokens", state.inkRibbonGraceTokens)
            .putInt("specimen_tier", state.unlockedSpecimenTier)
            .putBoolean("leon_overlay", state.leonOverlayEnabled)
            .putBoolean("axo_roam", state.axolotlRoamingEnabled)
            .putInt("axo_hunger", state.axolotlHunger)
            .putInt("axo_affection", state.axolotlAffection)
            .putInt("pet_count", state.petCountToday)
            .putBoolean("care_alerts", state.careAlertsEnabled)
            .putBoolean("auto_alarm", state.autoSetAlarmOnSchedule)
            .putBoolean("auto_calendar", state.autoSyncCalendarOnSchedule)
            .putString("signed_gmail", state.signedInGmail)
            .putInt("completed_sessions", state.completedSessions)
            .putInt("zero_distraction_sessions", state.zeroDistractionSessions)
            .putInt("ig_mins_today", state.instagramMinutesToday)
            .putInt("sprays_left", state.firstAidSpraysLeft)
            .putInt("herb_points", state.herbPoints)
            .putBoolean("shiny_axolotl", state.shinyAxolotlUnlocked)
            .putInt("shiny_count", state.shinyCount)
            .putBoolean("crt_enabled", state.crtScanlinesEnabled)
            .putBoolean("term_theme", state.terminalThemeActive)
            .putStringSet("blocked_packages", state.blockedPackages)
            .putString("todos_json", serializeTodos(state.todos))
            .apply()
    }

    fun recordDailyProgress(current: PlushieUiState): PlushieUiState {
        val today = LocalDate.now().toEpochDay()
        val nextStreak = if (current.lastActiveEpochDay < today) current.streakDays + 1 else current.streakDays
        return current.copy(
            streakDays = nextStreak,
            lastActiveEpochDay = today
        )
    }

    private fun serializeTodos(todos: List<TodoTask>): String {
        val arr = JSONArray()
        todos.forEach { t ->
            val obj = JSONObject()
            obj.put("id", t.id)
            obj.put("title", t.title)
            if (t.dueEpochMs != null) obj.put("dueEpochMs", t.dueEpochMs)
            obj.put("done", t.done)
            obj.put("shiny", t.shiny)
            obj.put("calendarSynced", t.calendarSynced)
            obj.put("alarmSet", t.alarmSet)
            arr.put(obj)
        }
        return arr.toString()
    }

    private fun parseTodos(raw: String?): List<TodoTask>? {
        if (raw.isNullOrBlank()) return null
        return try {
            val arr = JSONArray(raw)
            (0 until arr.length()).map { idx ->
                val obj = arr.getJSONObject(idx)
                TodoTask(
                    id = obj.optString("id", "t-$idx"),
                    title = obj.optString("title", "Untitled task"),
                    dueEpochMs = if (obj.has("dueEpochMs") && !obj.isNull("dueEpochMs")) obj.getLong("dueEpochMs") else null,
                    done = obj.optBoolean("done", false),
                    shiny = obj.optBoolean("shiny", false),
                    calendarSynced = obj.optBoolean("calendarSynced", false),
                    alarmSet = obj.optBoolean("alarmSet", false)
                )
            }
        } catch (_: Exception) {
            null
        }
    }
}

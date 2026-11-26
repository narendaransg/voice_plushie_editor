package com.raccoon.plushie

import android.accounts.AccountManager
import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.Bundle
import com.raccoon.plushie.audio.SaveRoomSoundEffects
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.raccoon.plushie.alarm.TaskAlarmScheduler
import com.raccoon.plushie.care.AxolotlCareCard
import com.raccoon.plushie.care.AxolotlCareService
import com.raccoon.plushie.care.RoamingAxolotlScreenLayer
import com.raccoon.plushie.data.PlushiePrefs
import com.raccoon.plushie.data.PlushieUiState
import com.raccoon.plushie.data.TodoTask
import com.raccoon.plushie.overlay.LeonOverlayService
import com.raccoon.plushie.poster.RemotePosterRepository
import com.raccoon.plushie.poster.FeedbackEntry
import com.raccoon.plushie.poster.SaveRoomPoster
import com.raccoon.plushie.sensors.SensorRig
import com.raccoon.plushie.service.ContainmentService
import com.raccoon.plushie.shell.TerminalEngine
import com.raccoon.plushie.ui.InstalledAppPickerDialog
import com.raccoon.plushie.ui.PlushiePocketTankCard
import com.raccoon.plushie.ui.theme.AmberNightOps
import com.raccoon.plushie.ui.theme.HerbGreen
import com.raccoon.plushie.ui.theme.HerbRed
import com.raccoon.plushie.ui.theme.HerbYellow
import com.raccoon.plushie.ui.theme.RaccoonPlushieTheme
import com.raccoon.plushie.ui.theme.ShinyAxolotlCyan
import kotlinx.coroutines.delay
import java.io.File
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {
    private var soundEffects: SaveRoomSoundEffects? = null

    private lateinit var prefsStore: PlushiePrefs
    private var sensorRig: SensorRig? = null
    private var stateHolder by mutableStateOf(PlushieUiState())

    private val syncReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            stateHolder = prefsStore.loadInitial().copy(
                usageAccessGranted = ContainmentService.hasUsageStatsPermission(this@MainActivity),
                overlayPermissionGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this@MainActivity),
                termuxInstalled = TerminalEngine.isTermuxInstalled(this@MainActivity)
            )
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        soundEffects = SaveRoomSoundEffects(this)
        prefsStore = PlushiePrefs(this)
        stateHolder = prefsStore.loadInitial().copy(
            usageAccessGranted = ContainmentService.hasUsageStatsPermission(this),
            overlayPermissionGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this),
            termuxInstalled = TerminalEngine.isTermuxInstalled(this)
        )

        if (stateHolder.careAlertsEnabled) {
            ContextCompat.startForegroundService(
                this,
                Intent(this, AxolotlCareService::class.java).apply { action = AxolotlCareService.ACTION_START_CARE }
            )
        }
        if (stateHolder.leonOverlayEnabled &&
            (Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this))
        ) {
            startLeonOverlayService()
        }

        val terminalLog = mutableStateListOf(
            "Save Room v0.6.0 ready. Frameless roaming axolotl, Leon HUD, streaks & live care tracker active."
        )

        sensorRig = SensorRig(
            context = this,
            onShakeDetected = {
                val nextShiny = stateHolder.shinyCount + 1
                val unlockAxo = stateHolder.shinyAxolotlUnlocked || nextShiny >= 2
                updateAndPersist {
                    it.copy(
                        herbPoints = it.herbPoints + 10,
                        shinyCount = nextShiny,
                        shinyAxolotlUnlocked = unlockAxo,
                        axolotlAffection = (it.axolotlAffection + 8).coerceAtMost(100),
                        bannerMessage = "Shake detected! Herbs mixed (+10 pts) & tilt shimmer charged.",
                        easterEggToast = if (unlockAxo && !it.shinyAxolotlUnlocked) {
                            "Rare Unlock: Specimen #AX-01 Shiny Blue Axolotl!"
                        } else "Gyro/Shake Tilt Shimmer Surge!"
                    )
                }
            },
            onFaceDownChanged = { faceDown ->
                updateAndPersist {
                    val now = System.currentTimeMillis()
                    val target = if (faceDown && !it.isTimerRunning) {
                        now + it.remainingSeconds * 1000L
                    } else {
                        it.targetEndTimeMs
                    }
                    it.copy(
                        stealthFaceDown = faceDown,
                        isTimerRunning = if (faceDown) true else it.isTimerRunning,
                        targetEndTimeMs = target,
                        bannerMessage = if (faceDown) {
                            "Face-down Stealth Mode active — hiding from threats & counting down."
                        } else {
                            "Phone lifted — Save Room watch active."
                        }
                    )
                }
            },
            onLowLightChanged = { lowLight ->
                updateAndPersist {
                    it.copy(
                        lowLightNightOps = lowLight,
                        bannerMessage = if (lowLight) {
                            "Low light detected — Amber Lantern NightOps active."
                        } else it.bannerMessage
                    )
                }
            },
            onTiltChanged = { px, rx ->
                stateHolder = stateHolder.copy(tiltX = px, tiltY = rx)
            }
        )

        setContent {
            var doorUnlocked by remember { mutableStateOf(false) }

            val uiState = stateHolder
            RaccoonPlushieTheme(terminalMode = uiState.terminalThemeActive) {
                if (!doorUnlocked) {
                    SaveRoomOpeningGate(
                        lowLightNightOps = uiState.lowLightNightOps,
                        onUnlockDoor = { reply ->
                            stateHolder = stateHolder.copy(
                                bannerMessage = "Save Room door opened ($reply)."
                            )
                            doorUnlocked = true
                        }
                    )
                    return@RaccoonPlushieTheme
                }

                LaunchedEffect(uiState.isTimerRunning, uiState.targetEndTimeMs) {
                    while (stateHolder.isTimerRunning) {
                        val cur = stateHolder
                        val now = System.currentTimeMillis()
                        val leftSec = if (cur.targetEndTimeMs > 0L) {
                            ((cur.targetEndTimeMs - now) / 1000L).toInt()
                        } else {
                            cur.remainingSeconds - 1
                        }
                        if (leftSec <= 0) {
                            stopContainmentService()
                            val nextCompleted = cur.completedSessions + 1
                            val zeroScrollBonus = if (cur.sessionDistractionHits == 0) 1 else 0
                            val nightOpsBonus = if (cur.lowLightNightOps) 15 else 0
                            val nextZero = cur.zeroDistractionSessions + zeroScrollBonus
                            val unlockAxo = cur.shinyAxolotlUnlocked || nextCompleted >= 2
                            updateAndPersist { prev ->
                                val withStreak = prefsStore.recordDailyProgress(prev)
                                withStreak.copy(
                                    isTimerRunning = false,
                                    targetEndTimeMs = 0L,
                                    remainingSeconds = withStreak.activeBlockMinutes * 60,
                                    completedSessions = nextCompleted,
                                    zeroDistractionSessions = nextZero,
                                    shinyCount = withStreak.shinyCount + zeroScrollBonus,
                                    herbPoints = withStreak.herbPoints + 25 + nightOpsBonus,
                                    shinyAxolotlUnlocked = unlockAxo,
                                    merchantAvailable = nextCompleted % 2 == 0,
                                    bannerMessage = "Save Room complete! Streak ${withStreak.streakDays}d (+${25 + nightOpsBonus} Herbs).",
                                    easterEggToast = if (zeroScrollBonus > 0) {
                                        "Zero-Scroll Challenge Cleared! +1 Shiny Foil Roll"
                                    } else {
                                        "STA Passed: WNS +0.42ns | Session Saved"
                                    }
                                )
                            }
                            TaskAlarmScheduler.showTaskNotification(
                                this@MainActivity,
                                9001,
                                "Save Room complete! Streak ${stateHolder.streakDays}d"
                            )
                            break
                        } else {
                            stateHolder = cur.copy(remainingSeconds = leftSec)
                            prefsStore.save(stateHolder)
                        }
                        delay(1000L)
                    }
                }

                PlushieSaveRoomScreen(
                    uiState = uiState,
                    terminalLines = terminalLog,
                    workDir = filesDir,
                    onToggleTimer = {
                        val cur = stateHolder
                        if (cur.isTimerRunning) {
                            stopContainmentService()
                            val now = System.currentTimeMillis()
                            val rem = if (cur.targetEndTimeMs > 0L) {
                                ((cur.targetEndTimeMs - now) / 1000L).toInt().coerceAtLeast(1)
                            } else {
                                cur.remainingSeconds.coerceAtLeast(1)
                            }
                            updateAndPersist {
                                it.copy(
                                    isTimerRunning = false,
                                    remainingSeconds = rem,
                                    targetEndTimeMs = 0L,
                                    bannerMessage = "Save Room timer paused (persisted)."
                                )
                            }
                        } else {
                            val sec = if (cur.remainingSeconds <= 0) cur.activeBlockMinutes * 60 else cur.remainingSeconds
                            val targetMs = System.currentTimeMillis() + sec * 1000L
                            if (!cur.timerModeBreak) startContainmentService(cur.blockedPackages)
                            updateAndPersist {
                                it.copy(
                                    isTimerRunning = true,
                                    sessionDistractionHits = 0,
                                    remainingSeconds = sec,
                                    targetEndTimeMs = targetMs,
                                    bannerMessage = if (cur.timerModeBreak) {
                                        "Save Room Break active (${cur.breakMinutes}m)."
                                    } else {
                                        "Bio-Shield ON: ${cur.pomodoroMinutes}m study lock armed."
                                    }
                                )
                            }
                        }
                    },
                    onResetTimer = {
                        stopContainmentService()
                        updateAndPersist {
                            it.copy(
                                isTimerRunning = false,
                                targetEndTimeMs = 0L,
                                remainingSeconds = it.activeBlockMinutes * 60,
                                bannerMessage = "Timer reset to ${it.activeBlockMinutes}m."
                            )
                        }
                    },
                    onAddMinutes = { deltaMins ->
                        updateAndPersist { cur ->
                            val updatedSec = (cur.remainingSeconds + deltaMins * 60).coerceIn(60, 90 * 60)
                            val updatedTarget = if (cur.isTimerRunning) {
                                System.currentTimeMillis() + updatedSec * 1000L
                            } else 0L
                            cur.copy(
                                remainingSeconds = updatedSec,
                                targetEndTimeMs = updatedTarget,
                                bannerMessage = "Adjusted timer by +${deltaMins}m."
                            )
                        }
                    },
                    onToggleBreakMode = {
                        stopContainmentService()
                        updateAndPersist { cur ->
                            val nextBreak = !cur.timerModeBreak
                            val mins = if (nextBreak) cur.breakMinutes else cur.pomodoroMinutes
                            cur.copy(
                                timerModeBreak = nextBreak,
                                isTimerRunning = false,
                                targetEndTimeMs = 0L,
                                remainingSeconds = mins * 60,
                                bannerMessage = if (nextBreak) "Switched to Break mode (${mins}m)." else "Switched to Focus mode (${mins}m)."
                            )
                        }
                    },
                    onCycleFocusPreset = {
                        stopContainmentService()
                        val presets = listOf(15, 25, 50, 64)
                        val idx = presets.indexOf(stateHolder.pomodoroMinutes)
                        val nextMins = presets[(idx + 1) % presets.size]
                        val mcToast = if (nextMins == 64) "Minecraft 64-Stack Pomodoro unlocked!" else null
                        updateAndPersist {
                            it.copy(
                                timerModeBreak = false,
                                pomodoroMinutes = nextMins,
                                remainingSeconds = nextMins * 60,
                                targetEndTimeMs = 0L,
                                isTimerRunning = false,
                                bannerMessage = "Focus block set to ${nextMins} minutes.",
                                easterEggToast = mcToast
                            )
                        }
                    },
                    onBuySprayWithHerbs = {
                        val cur = stateHolder
                        if (cur.herbPoints < 20) {
                            updateAndPersist { it.copy(bannerMessage = "Need 20 Herbs to craft a First Aid Spray.") }
                        } else {
                            updateAndPersist {
                                it.copy(
                                    herbPoints = it.herbPoints - 20,
                                    firstAidSpraysLeft = it.firstAidSpraysLeft + 1,
                                    bannerMessage = "Crafted +1 First Aid Spray (-20 Herbs)."
                                )
                            }
                        }
                    },
                    onBuyInkGraceWithHerbs = {
                        val cur = stateHolder
                        if (cur.herbPoints < 30) {
                            updateAndPersist { it.copy(bannerMessage = "Need 30 Herbs to craft an Ink Ribbon Grace Token.") }
                        } else {
                            updateAndPersist {
                                it.copy(
                                    herbPoints = it.herbPoints - 30,
                                    inkRibbonGraceTokens = it.inkRibbonGraceTokens + 1,
                                    bannerMessage = "Crafted +1 Ink Ribbon Grace Token (-30 Herbs)."
                                )
                            }
                        }
                    },
                    onToggleLeonOverlay = {
                        val cur = stateHolder
                        val wantEnabled = !cur.leonOverlayEnabled
                        if (wantEnabled) {
                            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
                                startActivity(
                                    Intent(
                                        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                        android.net.Uri.parse("package:$packageName")
                                    )
                                )
                                return@PlushieSaveRoomScreen
                            }
                            startLeonOverlayService()
                        } else {
                            stopLeonOverlayService()
                        }
                        updateAndPersist {
                            it.copy(
                                leonOverlayEnabled = wantEnabled,
                                bannerMessage = if (wantEnabled) {
                                    "Leon Guard overlay ON — use Start/Pause & Pet from any screen."
                                } else {
                                    "Leon Guard overlay OFF."
                                }
                            )
                        }
                    },
                    onToggleRoaming = {
                        updateAndPersist {
                            val next = !it.axolotlRoamingEnabled
                            it.copy(
                                axolotlRoamingEnabled = next,
                                bannerMessage = if (next) "Axolotl left tank to swim and rest across UI." else "Axolotl returned safely to tank."
                            )
                        }
                    },
                    onToggleCareAlerts = {
                        val next = !stateHolder.careAlertsEnabled
                        updateAndPersist { it.copy(careAlertsEnabled = next) }
                        if (next) {
                            ContextCompat.startForegroundService(
                                this,
                                Intent(this, AxolotlCareService::class.java).apply { action = AxolotlCareService.ACTION_START_CARE }
                            )
                        } else {
                            startService(Intent(this, AxolotlCareService::class.java).apply { action = AxolotlCareService.ACTION_STOP_CARE })
                        }
                    },
                    onPetAxolotl = {
                        updateAndPersist { cur ->
                            val nextBond = (cur.axolotlAffection + 10).coerceAtMost(100)
                            val nextPets = cur.petCountToday + 1
                            val nextShiny = cur.shinyCount + (if (nextPets % 3 == 0) 1 else 0)
                            val unlock = cur.shinyAxolotlUnlocked || nextPets >= 2
                            cur.copy(
                                axolotlAffection = nextBond,
                                petCountToday = nextPets,
                                shinyCount = nextShiny,
                                shinyAxolotlUnlocked = unlock,
                                herbPoints = cur.herbPoints + 3,
                                bannerMessage = "Petted Shiny Axolotl! Bond $nextBond% (+3 Herbs).",
                                easterEggToast = "Axolotl happy wiggle! Tilt shimmer active."
                            )
                        }
                        refreshLiveCareNotification()
                    },
                    onFeedAxolotl = {
                        val cur = stateHolder
                        if (cur.herbPoints < 10) {
                            updateAndPersist { it.copy(bannerMessage = "Need 10 Herb points to feed the axolotl.") }
                            return@PlushieSaveRoomScreen
                        }
                        updateAndPersist {
                            val nextHunger = (it.axolotlHunger + 20).coerceAtMost(100)
                            val nextBond = (it.axolotlAffection + 6).coerceAtMost(100)
                            it.copy(
                                herbPoints = it.herbPoints - 10,
                                axolotlHunger = nextHunger,
                                axolotlAffection = nextBond,
                                shinyAxolotlUnlocked = true,
                                bannerMessage = "Fed tricolour herb treat! Fullness $nextHunger%, Bond $nextBond%."
                            )
                        }
                        refreshLiveCareNotification()
                    },
                    onToggleAutoAlarm = {
                        updateAndPersist { it.copy(autoSetAlarmOnSchedule = !it.autoSetAlarmOnSchedule) }
                    },
                    onToggleAutoCalendar = {
                        updateAndPersist { it.copy(autoSyncCalendarOnSchedule = !it.autoSyncCalendarOnSchedule) }
                    },
                    onPickGmailAccount = {
                        selectGoogleAccount()
                    },
                    onSignOutGmail = {
                        updateAndPersist {
                            it.copy(signedInGmail = null, bannerMessage = "Signed out of Gmail profile.")
                        }
                    },
                    onUseFirstAidSpray = {
                        if (stateHolder.firstAidSpraysLeft > 0) {
                            updateAndPersist {
                                it.copy(
                                    firstAidSpraysLeft = it.firstAidSpraysLeft - 1,
                                    bannerMessage = "First Aid Spray used (${it.firstAidSpraysLeft - 1} left today) — brief check allowed."
                                )
                            }
                        } else {
                            updateAndPersist {
                                it.copy(bannerMessage = "Out of First Aid Sprays! Craft one for 20 Herbs.")
                            }
                        }
                    },
                    onSimulateIgMinute = {
                        updateAndPersist {
                            val nextIg = it.instagramMinutesToday + 5
                            it.copy(
                                instagramMinutesToday = nextIg,
                                sessionDistractionHits = it.sessionDistractionHits + 1,
                                bannerMessage = "Logged +5m distraction time (${nextIg}m today)."
                            )
                        }
                    },
                    onTestAudio = {
                        // playOpeningPunchline handled via activity callback
                        // playTypewriterSave handled via activity callback
                    },
                    onTypewriterTap = {
                        updateAndPersist {
                            val nextCrt = !it.crtScanlinesEnabled
                            it.copy(
                                crtScanlinesEnabled = nextCrt,
                                bannerMessage = if (nextCrt) "Typewriter CRT scanlines ON." else "Typewriter CRT scanlines OFF."
                            )
                        }
                    },
                    onAddTodo = { title ->
                        updateAndPersist { cur ->
                            val newTask = TodoTask(
                                id = "t-${System.currentTimeMillis()}",
                                title = title,
                                shiny = cur.shinyAxolotlUnlocked
                            )
                            cur.copy(
                                todos = listOf(newTask) + cur.todos,
                                bannerMessage = "Added task to Attache Case: $title"
                            )
                        }
                    },
                    onToggleTodoDone = { id ->
                        val now = System.currentTimeMillis()
                        updateAndPersist { cur ->
                            var bonusHerbs = 0
                            var bonusShiny = 0
                            var onTimeReward = false
                            val updatedTodos = cur.todos.map { task ->
                                if (task.id == id) {
                                    val becomingDone = !task.done
                                    if (becomingDone) {
                                        val isOnTime = task.dueEpochMs == null || now <= task.dueEpochMs
                                        bonusHerbs = if (isOnTime) 15 else 5
                                        if (isOnTime) {
                                            bonusShiny = 1
                                            onTimeReward = true
                                        }
                                    }
                                    task.copy(done = becomingDone, shiny = task.shiny || onTimeReward)
                                } else {
                                    task
                                }
                            }
                            val nextShinyTotal = cur.shinyCount + bonusShiny
                            val withStreak = if (bonusHerbs > 0) prefsStore.recordDailyProgress(cur) else cur
                            withStreak.copy(
                                todos = updatedTodos,
                                herbPoints = withStreak.herbPoints + bonusHerbs,
                                shinyCount = nextShinyTotal,
                                shinyAxolotlUnlocked = withStreak.shinyAxolotlUnlocked || nextShinyTotal >= 2,
                                bannerMessage = if (onTimeReward) {
                                    "On-time task cleared! Streak ${withStreak.streakDays}d · +15 Herbs & +1 Foil."
                                } else {
                                    "Updated task status (+${bonusHerbs} Herbs)."
                                },
                                easterEggToast = if (onTimeReward) "Shiny Foil Reward: On-time clear!" else withStreak.easterEggToast
                            )
                        }
                    },
                    onScheduleTodo = { id, dueMs ->
                        val cur = stateHolder
                        val task = cur.todos.firstOrNull { it.id == id } ?: return@PlushieSaveRoomScreen
                        TaskAlarmScheduler.scheduleNotification(this, task.id, task.title, dueMs)
                        val alarmLaunched = if (cur.autoSetAlarmOnSchedule) {
                            TaskAlarmScheduler.openSystemAlarmSet(this, task.title, dueMs)
                        } else false
                        val calLaunched = if (cur.autoSyncCalendarOnSchedule) {
                            TaskAlarmScheduler.openCalendarInsert(this, task.title, dueMs, cur.signedInGmail)
                        } else false

                        updateAndPersist { st ->
                            st.copy(
                                todos = st.todos.map {
                                    if (it.id == id) {
                                        it.copy(
                                            dueEpochMs = dueMs,
                                            alarmSet = it.alarmSet || alarmLaunched,
                                            calendarSynced = it.calendarSynced || calLaunched
                                        )
                                    } else it
                                },
                                bannerMessage = "Scheduled '${task.title}' (alert${if (alarmLaunched) " + alarm" else ""}${if (calLaunched) " + calendar" else ""})."
                            )
                        }
                    },
                    onAddBlockedPkg = { pkg ->
                        updateAndPersist { cur ->
                            val nextSet = cur.blockedPackages + pkg.trim()
                            if (cur.isTimerRunning && !cur.timerModeBreak) startContainmentService(nextSet)
                            cur.copy(
                                blockedPackages = nextSet,
                                bannerMessage = "Added $pkg to Bio-Shield block list."
                            )
                        }
                    },
                    onRemoveBlockedPkg = { pkg ->
                        updateAndPersist { cur ->
                            val nextSet = cur.blockedPackages - pkg
                            if (cur.isTimerRunning && !cur.timerModeBreak) startContainmentService(nextSet)
                            cur.copy(
                                blockedPackages = nextSet,
                                bannerMessage = "Removed $pkg from Bio-Shield block list."
                            )
                        }
                    },
                    onOpenUsageSettings = {
                        startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
                    },
                    onOpenOverlaySettings = {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                            startActivity(
                                Intent(
                                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                    android.net.Uri.parse("package:$packageName")
                                )
                            )
                        }
                    },
                    onRunShellCommand = { raw ->
                        val res = TerminalEngine.execute(this, raw, filesDir)
                        terminalLog.add("> $raw")
                        if (res.output.isNotBlank()) {
                            res.output.lines().forEach { terminalLog.add(it) }
                        }
                        updateAndPersist { cur ->
                            val newMins = res.startPomodoroMinutes ?: cur.pomodoroMinutes
                            val shouldStart = res.startPomodoroMinutes != null
                            val targetMs = if (shouldStart) System.currentTimeMillis() + newMins * 60_000L else cur.targetEndTimeMs
                            if (shouldStart) startContainmentService(cur.blockedPackages)

                            val nextTodos = if (res.newTodoTitle != null) {
                                listOf(
                                    TodoTask(
                                        id = "t-${System.currentTimeMillis()}",
                                        title = res.newTodoTitle,
                                        shiny = cur.shinyAxolotlUnlocked
                                    )
                                ) + cur.todos
                            } else {
                                cur.todos
                            }

                            val nextBlocked = when {
                                res.blockPkgName != null -> cur.blockedPackages + res.blockPkgName
                                res.unblockPkgName != null -> cur.blockedPackages - res.unblockPkgName
                                else -> cur.blockedPackages
                            }

                            cur.copy(
                                timerModeBreak = if (shouldStart) false else cur.timerModeBreak,
                                pomodoroMinutes = newMins,
                                remainingSeconds = if (shouldStart) newMins * 60 else cur.remainingSeconds,
                                targetEndTimeMs = targetMs,
                                isTimerRunning = if (shouldStart) true else cur.isTimerRunning,
                                shinyAxolotlUnlocked = cur.shinyAxolotlUnlocked || res.unlockShinyAxolotl,
                                shinyCount = if (res.unlockShinyAxolotl) cur.shinyCount + 1 else cur.shinyCount,
                                terminalThemeActive = if (res.toggleTermTheme) !cur.terminalThemeActive else cur.terminalThemeActive,
                                herbPoints = cur.herbPoints + (if (res.mixHerbs) 10 else 0) + (if (res.triggerMerchant) 15 else 0),
                                merchantAvailable = cur.merchantAvailable || res.triggerMerchant,
                                todos = nextTodos,
                                blockedPackages = nextBlocked,
                                easterEggToast = when {
                                    res.unlockShinyAxolotl -> "Specimen #AX-01 Shiny Blue Axolotl summoned!"
                                    res.triggerMerchant -> "Merchant Stash opened: +15 Herb pts!"
                                    res.triggerMinecraftEgg -> "Minecraft Nether + Shiny Axolotl Easter Egg!"
                                    res.triggerStaReport -> "STA Report: WNS +0.42ns | TNS 0.00ns (PASS)"
                                    else -> cur.easterEggToast
                                }
                            )
                        }
                    }
                )
            }
        }
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter().apply {
            addAction(LeonOverlayService.ACTION_OVERLAY_STATE_CHANGED)
            addAction(AxolotlCareService.ACTION_CARE_UPDATED)
        }
        ContextCompat.registerReceiver(this, syncReceiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)
    }

    override fun onStop() {
        super.onStop()
        try {
            unregisterReceiver(syncReceiver)
        } catch (_: Exception) {
        }
    }

    @Suppress("DEPRECATION")
    private fun selectGoogleAccount() {
        val am = AccountManager.get(this)
        val existing = am.getAccountsByType("com.google")
        if (existing.isNotEmpty()) {
            val picked = existing.first().name
            updateAndPersist {
                it.copy(signedInGmail = picked, bannerMessage = "Connected Gmail account: $picked")
            }
            return
        }
        try {
            val intent = AccountManager.newChooseAccountIntent(
                null,
                null,
                arrayOf("com.google"),
                null,
                null,
                null,
                null
            )
            startActivityForResult(intent, 5021)
        } catch (_: Exception) {
            startActivity(Intent(Settings.ACTION_ADD_ACCOUNT).apply {
                putExtra(Settings.EXTRA_ACCOUNT_TYPES, arrayOf("com.google"))
            })
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 5021 && resultCode == RESULT_OK) {
            val email = data?.getStringExtra(AccountManager.KEY_ACCOUNT_NAME)
            if (!email.isNullOrBlank()) {
                updateAndPersist {
                    it.copy(signedInGmail = email, bannerMessage = "Signed in with Gmail: $email")
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        sensorRig?.start()
        val cur = prefsStore.loadInitial()
        val now = System.currentTimeMillis()
        val refreshedSec = if (cur.isTimerRunning && cur.targetEndTimeMs > 0L) {
            ((cur.targetEndTimeMs - now) / 1000L).toInt().coerceAtLeast(0)
        } else {
            cur.remainingSeconds
        }
        stateHolder = cur.copy(
            remainingSeconds = refreshedSec,
            isTimerRunning = if (cur.isTimerRunning && refreshedSec <= 0) false else cur.isTimerRunning,
            targetEndTimeMs = if (cur.isTimerRunning && refreshedSec <= 0) 0L else cur.targetEndTimeMs,
            usageAccessGranted = ContainmentService.hasUsageStatsPermission(this),
            overlayPermissionGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this),
            termuxInstalled = TerminalEngine.isTermuxInstalled(this)
        )
    }

    override fun onPause() {
        super.onPause()
        sensorRig?.stop()
        prefsStore.save(stateHolder)
    }

    private fun refreshLiveCareNotification() {
        if (stateHolder.careAlertsEnabled) {
            startService(Intent(this, AxolotlCareService::class.java).apply {
                action = AxolotlCareService.ACTION_REFRESH_NOW
            })
        }
    }

    private fun startLeonOverlayService() {
        val intent = Intent(this, LeonOverlayService::class.java).apply {
            action = LeonOverlayService.ACTION_START_LEON
        }
        ContextCompat.startForegroundService(this, intent)
    }

    private fun stopLeonOverlayService() {
        val intent = Intent(this, LeonOverlayService::class.java).apply {
            action = LeonOverlayService.ACTION_STOP_LEON
        }
        startService(intent)
    }

    private fun startContainmentService(blocked: Set<String>) {
        val intent = Intent(this, ContainmentService::class.java).apply {
            action = ContainmentService.ACTION_START_LOCK
            putStringArrayListExtra(ContainmentService.EXTRA_BLOCKED_PKGS, ArrayList(blocked))
        }
        ContextCompat.startForegroundService(this, intent)
    }

    private fun stopContainmentService() {
        val intent = Intent(this, ContainmentService::class.java).apply {
            action = ContainmentService.ACTION_STOP_LOCK
        }
        startService(intent)
    }

    private fun updateAndPersist(reducer: (PlushieUiState) -> PlushieUiState) {
        val updated = reducer(stateHolder)
        stateHolder = updated
        prefsStore.save(updated)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PlushieSaveRoomScreen(
    uiState: PlushieUiState,
    terminalLines: List<String>,
    workDir: File,
    onToggleTimer: () -> Unit,
    onResetTimer: () -> Unit,
    onAddMinutes: (Int) -> Unit,
    onToggleBreakMode: () -> Unit,
    onCycleFocusPreset: () -> Unit,
    onBuySprayWithHerbs: () -> Unit,
    onBuyInkGraceWithHerbs: () -> Unit,
    onToggleLeonOverlay: () -> Unit,
    onToggleRoaming: () -> Unit,
    onToggleCareAlerts: () -> Unit,
    onPetAxolotl: () -> Unit,
    onFeedAxolotl: () -> Unit,
    onToggleAutoAlarm: () -> Unit,
    onToggleAutoCalendar: () -> Unit,
    onPickGmailAccount: () -> Unit,
    onSignOutGmail: () -> Unit,
    onUseFirstAidSpray: () -> Unit,
    onSimulateIgMinute: () -> Unit,
    onTypewriterTap: () -> Unit,
    onTestAudio: () -> Unit,
    onAddTodo: (String) -> Unit,
    onToggleTodoDone: (String) -> Unit,
    onScheduleTodo: (String, Long) -> Unit,
    onAddBlockedPkg: (String) -> Unit,
    onRemoveBlockedPkg: (String) -> Unit,
    onOpenUsageSettings: () -> Unit,
    onOpenOverlaySettings: () -> Unit,
    onRunShellCommand: (String) -> Unit
) {
    val context = LocalContext.current
    var selectedTab by remember { mutableStateOf(0) }
    var cmdInput by remember { mutableStateOf("") }
    var newTodoText by remember { mutableStateOf("") }
    var newPkgText by remember { mutableStateOf("") }
    var showAppPicker by remember { mutableStateOf(false) }
    var pointerTargetPx by remember { mutableStateOf<Offset?>(null) }

    val mins = uiState.remainingSeconds / 60
    val secs = uiState.remainingSeconds % 60
    val formattedClock = String.format(Locale.getDefault(), "%02d:%02d", mins, secs)

    val shimmerTrans = rememberInfiniteTransition(label = "tilt_shimmer")
    val shimmerProgress by shimmerTrans.animateFloat(
        initialValue = -0.5f,
        targetValue = 1.5f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 2400, easing = { it }),
            repeatMode = RepeatMode.Restart
        ),
        label = "shimmer_sweep"
    )

    val nightOpsResId = remember {
        context.resources.getIdentifier("bg_night_ops", "drawable", context.packageName)
    }

    val herbColor = when {
        uiState.instagramMinutesToday >= 45 -> HerbRed
        uiState.instagramMinutesToday >= 20 -> HerbYellow
        else -> HerbGreen
    }

    val glassSurface = MaterialTheme.colorScheme.surface.copy(alpha = 0.74f)
    val sectionHeaderColor = if (uiState.lowLightNightOps) AmberNightOps else MaterialTheme.colorScheme.primary
    val shinyBrush = Brush.horizontalGradient(
        colors = listOf(ShinyAxolotlCyan, Color(0xFFA855F7), Color(0xFFF472B6), ShinyAxolotlCyan)
    )

    if (showAppPicker) {
        InstalledAppPickerDialog(
            alreadyBlocked = uiState.blockedPackages,
            onDismiss = { showAppPicker = false },
            onSelectPackage = { pkg ->
                onAddBlockedPkg(pkg)
                showAppPicker = false
            }
        )
    }

    fun pickDateTimeAndSchedule(taskId: String) {
        val cal = Calendar.getInstance()
        DatePickerDialog(
            context,
            { _, year, month, day ->
                TimePickerDialog(
                    context,
                    { _, hour, minute ->
                        val chosen = Calendar.getInstance().apply {
                            set(Calendar.YEAR, year)
                            set(Calendar.MONTH, month)
                            set(Calendar.DAY_OF_MONTH, day)
                            set(Calendar.HOUR_OF_DAY, hour)
                            set(Calendar.MINUTE, minute)
                            set(Calendar.SECOND, 0)
                        }
                        onScheduleTodo(taskId, chosen.timeInMillis)
                    },
                    cal.get(Calendar.HOUR_OF_DAY),
                    cal.get(Calendar.MINUTE),
                    false
                ).show()
            },
            cal.get(Calendar.YEAR),
            cal.get(Calendar.MONTH),
            cal.get(Calendar.DAY_OF_MONTH)
        ).show()
    }

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = if (uiState.lowLightNightOps) Color(0xFF140E05) else MaterialTheme.colorScheme.background
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .pointerInput(Unit) {
                    awaitEachGesture {
                        val down = awaitPointerEvent()
                        down.changes.firstOrNull()?.position?.let { pointerTargetPx = it }
                    }
                }
        ) {
            if (nightOpsResId != 0) {
                Image(
                    painter = painterResource(id = nightOpsResId),
                    contentDescription = "Save Room Amber Lantern",
                    modifier = Modifier
                        .fillMaxSize()
                        .alpha(if (uiState.lowLightNightOps) 0.44f else 0.24f),
                    contentScale = ContentScale.Crop
                )
            }

            Image(
                painter = painterResource(id = R.drawable.save_room_reticle),
                contentDescription = "Save Room Corner Frame",
                modifier = Modifier
                    .fillMaxSize()
                    .alpha(0.32f),
                contentScale = ContentScale.FillBounds
            )

            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                PlushiePocketTankCard(
                    shinyAxolotlUnlocked = uiState.shinyAxolotlUnlocked,
                    isRoamingOutside = uiState.axolotlRoamingEnabled,
                    isTimerRunning = uiState.isTimerRunning,
                    tiltX = uiState.tiltX,
                    tiltY = uiState.tiltY,
                    lowLightNightOps = uiState.lowLightNightOps,
                    herbPoints = uiState.herbPoints,
                    firstAidSpraysLeft = uiState.firstAidSpraysLeft
                )

                val tabTitles = listOf("Save Room", "Care & Shield", "Attache Case", "Field & Comms")
                ScrollableTabRow(
                    selectedTabIndex = selectedTab,
                    containerColor = glassSurface,
                    contentColor = if (uiState.lowLightNightOps) AmberNightOps else ShinyAxolotlCyan,
                    edgePadding = 4.dp,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                ) {
                    tabTitles.forEachIndexed { idx, label ->
                        Tab(
                            selected = selectedTab == idx,
                            onClick = { selectedTab = idx },
                            text = {
                                Text(
                                    text = label,
                                    fontWeight = if (selectedTab == idx) FontWeight.Bold else FontWeight.Medium,
                                    style = MaterialTheme.typography.labelMedium
                                )
                            }
                        )
                    }
                }

                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    if (selectedTab == 0) {
                        item {
                            Card(
                                colors = CardDefaults.cardColors(containerColor = glassSurface),
                                border = BorderStroke(
                                    1.dp,
                                    if (uiState.shinyAxolotlUnlocked) ShinyAxolotlCyan else herbColor
                                ),
                                modifier = Modifier.graphicsLayer {
                                    rotationX = (uiState.tiltY * 6f).coerceIn(-6f, 6f)
                                    rotationY = (uiState.tiltX * 6f).coerceIn(-6f, 6f)
                                    translationX = (uiState.tiltX * 6f).coerceIn(-6f, 6f)
                                    translationY = (uiState.tiltY * 6f).coerceIn(-6f, 6f)
                                }
                            ) {
                                Box(modifier = Modifier.fillMaxWidth()) {
                                    if (uiState.shinyAxolotlUnlocked) {
                                        Image(
                                            painter = painterResource(id = R.drawable.fx_foil_sweep),
                                            contentDescription = "Iridescent Foil Sweep",
                                            modifier = Modifier
                                                .matchParentSize()
                                                .offset(x = (shimmerProgress * 90f).dp)
                                                .alpha(0.30f),
                                            contentScale = ContentScale.Crop
                                        )
                                    }
                                    Column(modifier = Modifier.padding(14.dp)) {
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Text(
                                                text = if (uiState.shinyAxolotlUnlocked) {
                                                    "SAVE ROOM · FOIL x${uiState.shinyCount} · STREAK ${uiState.streakDays}d"
                                                } else {
                                                    "SAVE ROOM — BIOHAZARD CONTAINMENT"
                                                },
                                                style = MaterialTheme.typography.titleMedium,
                                                fontWeight = FontWeight.Bold,
                                                color = if (uiState.shinyAxolotlUnlocked) ShinyAxolotlCyan else herbColor,
                                                modifier = Modifier.weight(1f)
                                            )
                                            Spacer(modifier = Modifier.width(8.dp))
                                            Image(
                                                painter = painterResource(id = R.drawable.leon_chibi_plush),
                                                contentDescription = "Leon Guard",
                                                modifier = Modifier.size(48.dp)
                                            )
                                        }
                                        Spacer(modifier = Modifier.height(4.dp))
                                        Text(
                                            text = uiState.bannerMessage,
                                            style = MaterialTheme.typography.bodySmall,
                                            color = if (uiState.lowLightNightOps) Color(0xFFFDE68A) else Color(0xFFF3F4F6)
                                        )
                                        Spacer(modifier = Modifier.height(6.dp))
                                        Text(
                                            text = "Vitality: ${uiState.herbStatus} · Blocked: ${uiState.blockedPackages.size} · Sessions: ${uiState.completedSessions}",
                                            style = MaterialTheme.typography.labelSmall,
                                            color = herbColor
                                        )
                                        Text(
                                            text = "Sensors: Stealth=${if (uiState.stealthFaceDown) "ON" else "OFF"} · NightOps=${if (uiState.lowLightNightOps) "ON" else "OFF"} · Tilt=(${"%.2f".format(uiState.tiltX)}, ${"%.2f".format(uiState.tiltY)})",
                                            style = MaterialTheme.typography.labelSmall,
                                            color = ShinyAxolotlCyan
                                        )
                                        uiState.easterEggToast?.let { egg ->
                                            Spacer(modifier = Modifier.height(8.dp))
                                            Box(
                                                modifier = Modifier
                                                    .fillMaxWidth()
                                                    .clip(RoundedCornerShape(8.dp))
                                                    .background(shinyBrush)
                                                    .padding(8.dp)
                                            ) {
                                                Text(
                                                    text = egg,
                                                    color = Color(0xFF061018),
                                                    fontWeight = FontWeight.Bold,
                                                    style = MaterialTheme.typography.labelMedium
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        item {
                            Card(
                                colors = CardDefaults.cardColors(containerColor = glassSurface),
                                border = BorderStroke(1.dp, HerbGreen.copy(alpha = 0.45f))
                            ) {
                                Column(
                                    modifier = Modifier.padding(14.dp),
                                    verticalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    Text(
                                        text = "${if (uiState.timerModeBreak) "BREAK" else "POMODORO SAFE ROOM"}: $formattedClock (${uiState.activeBlockMinutes}m)",
                                        style = MaterialTheme.typography.titleLarge,
                                        fontWeight = FontWeight.Bold,
                                        fontFamily = FontFamily.Monospace,
                                        color = if (uiState.lowLightNightOps) Color(0xFFFEF08A) else Color(0xFFF3F4F6)
                                    )
                                    FlowRow(
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                                        verticalArrangement = Arrangement.spacedBy(6.dp)
                                    ) {
                                        Button(onClick = onToggleTimer) {
                                            Text(if (uiState.isTimerRunning) "Pause" else "Start Save Room")
                                        }
                                        OutlinedButton(onClick = onResetTimer) {
                                            Text("Reset")
                                        }
                                        OutlinedButton(onClick = onToggleBreakMode) {
                                            Text(if (uiState.timerModeBreak) "Focus Mode" else "Break Mode")
                                        }
                                        OutlinedButton(onClick = onCycleFocusPreset) {
                                            Text("Preset (${uiState.pomodoroMinutes}m)")
                                        }
                                        OutlinedButton(onClick = { onAddMinutes(1) }) {
                                            Text("+1m")
                                        }
                                        OutlinedButton(onClick = { onAddMinutes(5) }) {
                                            Text("+5m")
                                        }
                                        OutlinedButton(onClick = onToggleLeonOverlay) {
                                            Text(if (uiState.leonOverlayEnabled) "Leon Overlay: ON" else "Show Leon Overlay")
                                        }
                                        OutlinedButton(onClick = onUseFirstAidSpray) {
                                            Text("Spray (${uiState.firstAidSpraysLeft})")
                                        }
                                        OutlinedButton(onClick = onSimulateIgMinute) {
                                            Text("+5m Log")
                                        }
                                        OutlinedButton(onClick = onTypewriterTap) {
                                            Text(if (uiState.crtScanlinesEnabled) "CRT: ON" else "CRT")
                                        }
                                        OutlinedButton(onClick = {
                                            // playOpeningPunchline handled via activity callback
                                            // playTypewriterSave handled via activity callback
                                        }) {
                                            Text("Test Audio")
                                        }
                                    }
                                    if (!uiState.usageAccessGranted || !uiState.overlayPermissionGranted) {
                                        FlowRow(
                                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                                            verticalArrangement = Arrangement.spacedBy(6.dp)
                                        ) {
                                            if (!uiState.usageAccessGranted) {
                                                OutlinedButton(onClick = onOpenUsageSettings) {
                                                    Text("Grant Usage Access")
                                                }
                                            }
                                            if (!uiState.overlayPermissionGranted) {
                                                OutlinedButton(onClick = onOpenOverlaySettings) {
                                                    Text("Grant Overlay")
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        item {
                            var activePoster by remember { mutableStateOf<SaveRoomPoster?>(null) }
                            var posterUrlInput by remember { mutableStateOf(RemotePosterRepository.getConfiguredUrl(context)) }
                            var showPosterConfig by remember { mutableStateOf(false) }

                            LaunchedEffect(posterUrlInput) {
                                activePoster = RemotePosterRepository.fetchActivePoster(context, 1)
                            }

                            Card(
                                colors = CardDefaults.cardColors(containerColor = glassSurface),
                                border = BorderStroke(1.dp, AmberNightOps.copy(alpha = 0.65f))
                            ) {
                                Box(modifier = Modifier.fillMaxWidth()) {
                                    Image(
                                        painter = painterResource(id = R.drawable.save_room_poster_frame),
                                        contentDescription = "Save Room Wax Seal Frame",
                                        modifier = Modifier
                                            .matchParentSize()
                                            .alpha(0.35f),
                                        contentScale = ContentScale.FillBounds
                                    )
                                    Column(
                                        modifier = Modifier.padding(16.dp),
                                        verticalArrangement = Arrangement.spacedBy(8.dp)
                                    ) {
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Text(
                                                text = activePoster?.badgeTag ?: "CREATOR DISPATCH · STANDBY",
                                                style = MaterialTheme.typography.labelSmall,
                                                fontWeight = FontWeight.Bold,
                                                color = AmberNightOps
                                            )
                                            OutlinedButton(onClick = { showPosterConfig = !showPosterConfig }) {
                                                Text(if (showPosterConfig) "Close Feed" else "Feed URL")
                                            }
                                        }

                                        if (activePoster != null) {
                                            Text(
                                                text = activePoster!!.title,
                                                style = MaterialTheme.typography.titleSmall,
                                                fontWeight = FontWeight.Bold,
                                                color = ShinyAxolotlCyan
                                            )
                                            Text(
                                                text = activePoster!!.message,
                                                style = MaterialTheme.typography.bodySmall
                                            )
                                            Button(
                                                onClick = {
                                                    RemotePosterRepository.dismissPoster(context, activePoster!!.posterId)
                                                    activePoster = null
                                                }
                                            ) {
                                                Text("Acknowledge & Dismiss")
                                            }
                                        } else {
                                            Text(
                                                text = "No unread dispatches. Set an HTTPS JSON feed URL to push posters/messages.",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = if (uiState.lowLightNightOps) Color(0xFFFEF3C7) else Color(0xFFD1D5DB)
                                            )
                                        }

                                        if (showPosterConfig) {
                                            OutlinedTextField(
                                                value = posterUrlInput,
                                                onValueChange = { posterUrlInput = it },
                                                modifier = Modifier.fillMaxWidth(),
                                                singleLine = true,
                                                placeholder = { Text("https://.../poster.json") }
                                            )
                                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                                Button(
                                                    onClick = {
                                                        RemotePosterRepository.saveAdminFeedConfig(context, posterUrlInput, RemotePosterRepository.getAdminId(context), RemotePosterRepository.getSigningKey(context))
                                                        RemotePosterRepository.resetDismissed(context)
                                                    }
                                                ) {
                                                    Text("Save HTTPS Feed")
                                                }
                                                OutlinedButton(
                                                    onClick = {
                                                        RemotePosterRepository.resetDismissed(context)
                                                    }
                                                ) {
                                                    Text("Replay Poster")
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        item {
                            Card(
                                colors = CardDefaults.cardColors(containerColor = glassSurface),
                                border = BorderStroke(1.dp, AmberNightOps.copy(alpha = 0.55f))
                            ) {
                                Column(
                                    modifier = Modifier.padding(14.dp),
                                    verticalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                                    ) {
                                        Image(
                                            painter = painterResource(id = R.drawable.specimen_milestone_badge),
                                            contentDescription = "Specimen Milestone Crest",
                                            modifier = Modifier.size(54.dp)
                                        )
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                text = "STREAK: ${uiState.streakDays} DAY(S) · ${uiState.rankTitle}",
                                                style = MaterialTheme.typography.titleSmall,
                                                fontWeight = FontWeight.Bold,
                                                color = AmberNightOps
                                            )
                                            Text(
                                                text = "${uiState.specimenVariantLabel} · Ink Grace: ${uiState.inkRibbonGraceTokens}",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = ShinyAxolotlCyan
                                            )
                                            Text(
                                                text = "Zero-Scroll Runs: ${uiState.zeroDistractionSessions} · Foil: ${uiState.shinyCount}",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = if (uiState.lowLightNightOps) Color(0xFFFEF3C7) else Color(0xFFD1D5DB)
                                            )
                                        }
                                    }
                                    FlowRow(
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                                        verticalArrangement = Arrangement.spacedBy(6.dp)
                                    ) {
                                        OutlinedButton(onClick = onBuySprayWithHerbs) {
                                            Text("Craft Spray (-20 Herbs)")
                                        }
                                        OutlinedButton(onClick = onBuyInkGraceWithHerbs) {
                                            Text("Ink Grace (-30 Herbs)")
                                        }
                                    }
                                }
                            }
                        }
                    } else if (selectedTab == 1) {
                        item {
                            AxolotlCareCard(
                                hunger = uiState.axolotlHunger,
                                affection = uiState.axolotlAffection,
                                petCountToday = uiState.petCountToday,
                                roamingEnabled = uiState.axolotlRoamingEnabled,
                                careAlertsEnabled = uiState.careAlertsEnabled,
                                herbPoints = uiState.herbPoints,
                                onToggleRoaming = onToggleRoaming,
                                onToggleCareAlerts = onToggleCareAlerts,
                                onPetAxolotl = onPetAxolotl,
                                onFeedAxolotl = onFeedAxolotl
                            )
                        }

                        item {
                            Card(
                                colors = CardDefaults.cardColors(containerColor = glassSurface),
                                border = BorderStroke(1.dp, Color(0xFF2B3D34))
                            ) {
                                Column(
                                    modifier = Modifier.padding(14.dp),
                                    verticalArrangement = Arrangement.spacedBy(6.dp)
                                ) {
                                    Text(
                                        text = "10s WARNING + AUTO-EXIT BLOCK LIST",
                                        style = MaterialTheme.typography.titleSmall,
                                        fontWeight = FontWeight.Bold,
                                        color = sectionHeaderColor
                                    )
                                    Text(
                                        text = "During focus blocks, opening a blocked app shows a 10s warning and then exits back to Home.",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = if (uiState.lowLightNightOps) Color(0xFFFEF3C7) else Color(0xFFD1D5DB)
                                    )
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text("Installed Apps", style = MaterialTheme.typography.labelMedium)
                                        OutlinedButton(onClick = { showAppPicker = true }) {
                                            Text("Pick App")
                                        }
                                    }
                                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                        OutlinedTextField(
                                            value = newPkgText,
                                            onValueChange = { newPkgText = it },
                                            modifier = Modifier.weight(1f),
                                            singleLine = true,
                                            placeholder = { Text("com.package.name") }
                                        )
                                        Button(
                                            onClick = {
                                                if (newPkgText.isNotBlank()) {
                                                    onAddBlockedPkg(newPkgText)
                                                    newPkgText = ""
                                                }
                                            }
                                        ) {
                                            Text("Block")
                                        }
                                    }
                                    uiState.blockedPackages.forEach { pkg ->
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Text(
                                                text = pkg,
                                                fontFamily = FontFamily.Monospace,
                                                style = MaterialTheme.typography.bodySmall
                                            )
                                            OutlinedButton(onClick = { onRemoveBlockedPkg(pkg) }) {
                                                Text("Remove")
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    } else if (selectedTab == 2) {
                        item {
                            Card(
                                colors = CardDefaults.cardColors(containerColor = glassSurface),
                                border = BorderStroke(1.dp, Color(0xFF2B3D34))
                            ) {
                                Column(
                                    modifier = Modifier.padding(14.dp),
                                    verticalArrangement = Arrangement.spacedBy(6.dp)
                                ) {
                                    Text(
                                        text = "ALARM, GOOGLE CALENDAR & GMAIL SIGN-IN",
                                        style = MaterialTheme.typography.titleSmall,
                                        fontWeight = FontWeight.Bold,
                                        color = sectionHeaderColor
                                    )
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text("Set System Alarm on Schedule", style = MaterialTheme.typography.bodySmall)
                                        Switch(checked = uiState.autoSetAlarmOnSchedule, onCheckedChange = { onToggleAutoAlarm() })
                                    }
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text("Open Google Calendar on Schedule", style = MaterialTheme.typography.bodySmall)
                                        Switch(checked = uiState.autoSyncCalendarOnSchedule, onCheckedChange = { onToggleAutoCalendar() })
                                    }
                                    Text(
                                        text = "Gmail Profile: ${uiState.signedInGmail ?: "Not signed in"}",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = if (uiState.signedInGmail != null) HerbGreen else AmberNightOps
                                    )
                                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Button(onClick = onPickGmailAccount) {
                                            Text(if (uiState.signedInGmail != null) "Switch Gmail" else "Gmail Sign-In")
                                        }
                                        if (uiState.signedInGmail != null) {
                                            OutlinedButton(onClick = onSignOutGmail) {
                                                Text("Sign Out")
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        item {
                            Text(
                                text = "ATTACHE CASE TO-DO & SCHEDULED ALARMS",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.Bold,
                                color = sectionHeaderColor
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                OutlinedTextField(
                                    value = newTodoText,
                                    onValueChange = { newTodoText = it },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                    placeholder = { Text("New study task or goal...") }
                                )
                                Button(
                                    onClick = {
                                        if (newTodoText.isNotBlank()) {
                                            onAddTodo(newTodoText.trim())
                                            newTodoText = ""
                                        }
                                    }
                                ) {
                                    Text("Add")
                                }
                            }
                        }

                        items(uiState.todos, key = { it.id }) { task ->
                            val fmt = remember { SimpleDateFormat("dd MMM, hh:mm a", Locale.getDefault()) }
                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                colors = CardDefaults.cardColors(containerColor = glassSurface),
                                border = BorderStroke(1.dp, if (task.shiny) ShinyAxolotlCyan else Color(0xFF26362E))
                            ) {
                                Column(modifier = Modifier.padding(10.dp)) {
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        modifier = Modifier.fillMaxWidth()
                                    ) {
                                        Row(
                                            verticalAlignment = Alignment.CenterVertically,
                                            modifier = Modifier.weight(1f)
                                        ) {
                                            Checkbox(
                                                checked = task.done,
                                                onCheckedChange = { onToggleTodoDone(task.id) }
                                            )
                                            if (task.shiny) {
                                                Image(
                                                    painter = painterResource(id = R.drawable.shiny_foil_badge),
                                                    contentDescription = "Shiny Foil",
                                                    modifier = Modifier.size(24.dp)
                                                )
                                                Spacer(modifier = Modifier.width(6.dp))
                                            }
                                            Column {
                                                Text(
                                                    text = task.title,
                                                    fontWeight = FontWeight.SemiBold,
                                                    color = if (task.shiny) ShinyAxolotlCyan else MaterialTheme.colorScheme.onSurface
                                                )
                                                val tags = buildList {
                                                    if (task.alarmSet) add("Alarm")
                                                    if (task.calendarSynced) add("Calendar")
                                                }.joinToString(" + ")
                                                val scheduleLabel = if (task.dueEpochMs != null) {
                                                    "Alert: ${fmt.format(Date(task.dueEpochMs))}${if (tags.isNotEmpty()) " ($tags)" else ""}"
                                                } else {
                                                    "Unscheduled"
                                                }
                                                Text(
                                                    text = scheduleLabel,
                                                    style = MaterialTheme.typography.labelSmall,
                                                    color = if (uiState.lowLightNightOps) Color(0xFFFEF3C7) else Color(0xFFD1D5DB)
                                                )
                                            }
                                        }
                                        OutlinedButton(onClick = { pickDateTimeAndSchedule(task.id) }) {
                                            Text("Schedule")
                                        }
                                    }
                                }
                            }
                        }
                    } else {
                        item {
                            var tutorialDone by remember { mutableStateOf(RemotePosterRepository.isTutorialCompleted(context)) }
                            var tutorialStep by remember { mutableStateOf(0) }
                            val steps = remember {
                                listOf(
                                    "1/4 Leon Overlay: Toggle 'Show Leon Overlay' to float Leon outside the app. Tap him to toggle quick actions and drag anywhere.",
                                    "2/4 Roaming & Caring for #AX-01: The axolotl swims free with no box, rests on UI blocks, and follows your finger occasionally.",
                                    "3/4 10s Exit Shield & Streaks: Opening a blocked app during focus shows a 10s warning and exits to Home. Complete blocks daily to grow streaks.",
                                    "4/4 Repo Posters & Feedback: Connect an HTTPS JSON feed to push posters, and log/share feedback or suggestions below."
                                )
                            }

                            Card(
                                colors = CardDefaults.cardColors(containerColor = glassSurface),
                                border = BorderStroke(1.dp, ShinyAxolotlCyan.copy(alpha = 0.65f))
                            ) {
                                Column(
                                    modifier = Modifier.padding(14.dp),
                                    verticalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text(
                                            text = if (!tutorialDone) "FIRST-TIME SAVE ROOM TUTORIAL" else "SAVE ROOM FIELD GUIDE",
                                            style = MaterialTheme.typography.titleSmall,
                                            fontWeight = FontWeight.Bold,
                                            color = ShinyAxolotlCyan
                                        )
                                        OutlinedButton(
                                            onClick = {
                                                tutorialDone = false
                                                tutorialStep = (tutorialStep + 1) % steps.size
                                                RemotePosterRepository.setTutorialCompleted(context, false)
                                            }
                                        ) {
                                            Text(if (!tutorialDone) "Next Tip" else "Replay Tour")
                                        }
                                    }
                                    Text(steps[tutorialStep], style = MaterialTheme.typography.bodySmall)
                                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        OutlinedButton(
                                            onClick = {
                                                tutorialStep = (tutorialStep - 1 + steps.size) % steps.size
                                                tutorialDone = false
                                            }
                                        ) {
                                            Text("Prev")
                                        }
                                        Button(
                                            onClick = {
                                                if (tutorialStep < steps.lastIndex) {
                                                    tutorialStep += 1
                                                } else {
                                                    tutorialDone = true
                                                    RemotePosterRepository.setTutorialCompleted(context, true)
                                                }
                                            }
                                        ) {
                                            Text(if (tutorialStep < steps.lastIndex) "Next" else "Finish Tour")
                                        }
                                    }
                                }
                            }
                        }

                        item {
                            var fbCategory by remember { mutableStateOf("Suggestion") }
                            var fbNote by remember { mutableStateOf("") }
                            var fbList by remember { mutableStateOf(RemotePosterRepository.loadFeedback(context)) }

                            Card(
                                colors = CardDefaults.cardColors(containerColor = glassSurface),
                                border = BorderStroke(1.dp, HerbGreen.copy(alpha = 0.55f))
                            ) {
                                Column(
                                    modifier = Modifier.padding(14.dp),
                                    verticalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    Text(
                                        text = "FEEDBACK & SUGGESTIONS CORNER",
                                        style = MaterialTheme.typography.titleSmall,
                                        fontWeight = FontWeight.Bold,
                                        color = HerbGreen
                                    )
                                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                        listOf("Suggestion", "Feature", "UI / Bug").forEach { cat ->
                                            if (fbCategory == cat) {
                                                Button(onClick = { fbCategory = cat }) { Text(cat) }
                                            } else {
                                                OutlinedButton(onClick = { fbCategory = cat }) { Text(cat) }
                                            }
                                        }
                                    }
                                    OutlinedTextField(
                                        value = fbNote,
                                        onValueChange = { fbNote = it },
                                        modifier = Modifier.fillMaxWidth(),
                                        singleLine = false,
                                        minLines = 2,
                                        placeholder = { Text("Write a suggestion, idea, or note for the creator...") }
                                    )
                                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Button(
                                            onClick = {
                                                if (fbNote.isNotBlank()) {
                                                    fbList = RemotePosterRepository.addFeedback(context, fbCategory, fbNote)
                                                    fbNote = ""
                                                }
                                            }
                                        ) {
                                            Text("Save Note")
                                        }
                                        OutlinedButton(
                                            onClick = {
                                                context.startActivity(
                                                    Intent.createChooser(
                                                        RemotePosterRepository.shareFeedbackIntent(fbList),
                                                        "Send Feedback & Suggestions"
                                                    )
                                                )
                                            }
                                        ) {
                                            Text("Share (${fbList.size})")
                                        }
                                    }
                                    fbList.take(3).forEach { entry: FeedbackEntry ->
                                        Text(
                                            text = "• [${entry.category}] ${entry.note}",
                                            style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.85f)
                                        )
                                    }
                                }
                            }
                        }

                        item {
                            Card(
                                colors = CardDefaults.cardColors(containerColor = glassSurface),
                                border = BorderStroke(1.dp, Color(0xFF2B3D34))
                            ) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    Image(
                                        painter = painterResource(id = R.drawable.save_room_typewriter),
                                        contentDescription = "Save Room Typewriter",
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .height(86.dp),
                                        contentScale = ContentScale.Fit
                                    )
                                    Spacer(modifier = Modifier.height(6.dp))
                                    Text(
                                        text = "LIVE SHELL + TERMUX BRIDGE (${if (uiState.termuxInstalled) "Termux Found" else "Built-in sh"})",
                                        style = MaterialTheme.typography.titleSmall,
                                        fontWeight = FontWeight.Bold,
                                        color = sectionHeaderColor
                                    )
                                    Spacer(modifier = Modifier.height(6.dp))
                                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                        OutlinedTextField(
                                            value = cmdInput,
                                            onValueChange = { cmdInput = it },
                                            modifier = Modifier.weight(1f),
                                            singleLine = true,
                                            placeholder = { Text("todo Review FSM / block <pkg> / save-apk") }
                                        )
                                        Button(
                                            onClick = {
                                                if (cmdInput.isNotBlank()) {
                                                    onRunShellCommand(cmdInput)
                                                    cmdInput = ""
                                                }
                                            }
                                        ) {
                                            Text("Run")
                                        }
                                    }
                                    Spacer(modifier = Modifier.height(8.dp))
                                    Column(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .background(Color(0xAA050806))
                                            .padding(10.dp)
                                    ) {
                                        Text(
                                            text = "cwd: ${workDir.absolutePath}",
                                            color = Color(0xFF9CA3AF),
                                            fontFamily = FontFamily.Monospace,
                                            style = MaterialTheme.typography.labelSmall
                                        )
                                        terminalLines.takeLast(8).forEach { line ->
                                            Text(
                                                text = line,
                                                color = Color(0xFF4ADE80),
                                                fontFamily = FontFamily.Monospace,
                                                style = MaterialTheme.typography.bodySmall
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            RoamingAxolotlScreenLayer(
                enabled = uiState.axolotlRoamingEnabled,
                hunger = uiState.axolotlHunger,
                affection = uiState.axolotlAffection,
                tiltX = uiState.tiltX,
                tiltY = uiState.tiltY,
                pointerTargetPx = pointerTargetPx,
                onPetAxolotl = onPetAxolotl
            )

            if (uiState.crtScanlinesEnabled) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .alpha(0.08f)
                        .background(
                            Brush.verticalGradient(
                                colors = listOf(Color.White, Color.Transparent, Color.White, Color.Transparent)
                            )
                        )
                )
            }
        }
    }
}



@Composable
private fun SaveRoomOpeningGate(
    lowLightNightOps: Boolean,
    onUnlockDoor: (String) -> Unit
) {
    val context = LocalContext.current
    val questions = remember {
        listOf(
            "SAVE ROOM CHECKPOINT: What ink color is loaded in the typewriter today?",
            "SPECIMEN #AX-01 CHECK: How many gills does your shiny axolotl wiggle when happy?",
            "PERIMETER CHECK: What is today's focus mission before doomscrolling?",
            "SAFE ROOM PASSCODE: Name one herb or study goal—any answer unlocks the door."
        )
    }
    val chosenQuestion = remember { questions.random() }
    var answerInput by remember { mutableStateOf("") }
    var openingAnim by remember { mutableStateOf(false) }

    val gateBgResId = remember {
        context.resources.getIdentifier("save_room_gate", "drawable", context.packageName)
    }
    val sealResId = remember {
        context.resources.getIdentifier("save_room_unlock_seal", "drawable", context.packageName)
    }

    LaunchedEffect(openingAnim) {
        if (openingAnim) {
            delay(550L)
            onUnlockDoor(answerInput.trim().ifBlank { "OVERRIDE_APPROVED" })
        }
    }

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = Color(0xFF0A100D)
    ) {
        Box(modifier = Modifier.fillMaxSize()) {
            if (gateBgResId != 0) {
                Image(
                    painter = painterResource(id = gateBgResId),
                    contentDescription = "Save Room Security Door",
                    modifier = Modifier
                        .fillMaxSize()
                        .alpha(if (openingAnim) 0.18f else 0.42f),
                    contentScale = ContentScale.Crop
                )
            }
            if (sealResId != 0) {
                Image(
                    painter = painterResource(id = sealResId),
                    contentDescription = "Save Room Seal",
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .padding(top = 36.dp)
                        .size(110.dp)
                        .alpha(0.75f),
                    contentScale = ContentScale.Fit
                )
            }

            Card(
                modifier = Modifier
                    .align(Alignment.Center)
                    .fillMaxWidth()
                    .padding(18.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.86f)),
                border = BorderStroke(1.5.dp, if (lowLightNightOps) AmberNightOps else HerbGreen)
            ) {
                Column(
                    modifier = Modifier.padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text(
                        text = if (openingAnim) "DOOR UNLOCKING · SAVE ROOM ENTERED" else "SAVE ROOM ENTRY VERIFICATION",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (lowLightNightOps) AmberNightOps else HerbGreen
                    )
                    Text(
                        text = chosenQuestion,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = ShinyAxolotlCyan
                    )
                    Text(
                        text = "Any answer—or tapping Open Door—clears the lock immediately.",
                        style = MaterialTheme.typography.labelSmall,
                        color = if (lowLightNightOps) Color(0xFFFEF3C7) else Color(0xFFD1D5DB)
                    )
                    OutlinedTextField(
                        value = answerInput,
                        onValueChange = { answerInput = it },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        placeholder = { Text("Type anything to unlock...") }
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Button(
                            onClick = { openingAnim = true },
                            enabled = !openingAnim
                        ) {
                            Text(if (openingAnim) "Opening..." else "Open Save Room Door")
                        }
                    }
                }
            }
        }
    }
}

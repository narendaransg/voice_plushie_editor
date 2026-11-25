package com.raccoon.plushie

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.raccoon.plushie.data.PlushiePrefs
import com.raccoon.plushie.data.PlushieUiState
import com.raccoon.plushie.data.StashEntry
import com.raccoon.plushie.sensors.SensorRig
import com.raccoon.plushie.service.ContainmentService
import com.raccoon.plushie.shell.TerminalEngine
import com.raccoon.plushie.ui.theme.AmberNightOps
import com.raccoon.plushie.ui.theme.HerbGreen
import com.raccoon.plushie.ui.theme.HerbRed
import com.raccoon.plushie.ui.theme.HerbYellow
import com.raccoon.plushie.ui.theme.RaccoonPlushieTheme
import com.raccoon.plushie.ui.theme.ShinyAxolotlCyan
import kotlinx.coroutines.delay
import java.io.File

class MainActivity : ComponentActivity() {

    private lateinit var prefsStore: PlushiePrefs
    private var sensorRig: SensorRig? = null
    private var stateHolder by mutableStateOf(PlushieUiState())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefsStore = PlushiePrefs(this)
        stateHolder = prefsStore.loadInitial().copy(
            usageAccessGranted = ContainmentService.hasUsageStatsPermission(this),
            overlayPermissionGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this),
            termuxInstalled = TerminalEngine.isTermuxInstalled(this)
        )

        val terminalLog = mutableStateListOf(
            "Save Room v0.1.0 initialized. Type 'help' or 'spawn axolotl'."
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
                        bannerMessage = "Shake detected! Herbs mixed (+10 pts) & shiny shimmer charged.",
                        easterEggToast = if (unlockAxo && !it.shinyAxolotlUnlocked) {
                            "Rare Unlock: Specimen #AX-01 Shiny Blue Axolotl!"
                        } else null
                    )
                }
            },
            onFaceDownChanged = { faceDown ->
                updateAndPersist {
                    it.copy(
                        stealthFaceDown = faceDown,
                        isTimerRunning = if (faceDown) true else it.isTimerRunning,
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
                            "Low light detected — Raccoon Midnight eye-comfort mode active."
                        } else it.bannerMessage
                    )
                }
            },
            onTiltChanged = { px, rx ->
                stateHolder = stateHolder.copy(tiltX = px, tiltY = rx)
            }
        )

        setContent {
            val uiState = stateHolder
            RaccoonPlushieTheme(terminalMode = uiState.terminalThemeActive) {
                LaunchedEffect(uiState.isTimerRunning) {
                    while (stateHolder.isTimerRunning && stateHolder.remainingSeconds > 0) {
                        delay(1000L)
                        val cur = stateHolder
                        if (!cur.isTimerRunning) break
                        if (cur.remainingSeconds <= 1) {
                            stopContainmentService()
                            val nextCompleted = cur.completedSessions + 1
                            val nextZero = cur.zeroDistractionSessions + 1
                            val unlockAxo = cur.shinyAxolotlUnlocked || nextCompleted >= 3
                            updateAndPersist {
                                it.copy(
                                    isTimerRunning = false,
                                    remainingSeconds = it.pomodoroMinutes * 60,
                                    completedSessions = nextCompleted,
                                    zeroDistractionSessions = nextZero,
                                    herbPoints = it.herbPoints + 25,
                                    shinyAxolotlUnlocked = unlockAxo,
                                    merchantAvailable = nextCompleted % 2 == 0,
                                    bannerMessage = "Save Room complete! Ink ribbon saved (+25 Herb pts).",
                                    easterEggToast = "STA Passed: WNS +0.42ns | Zero Instagram violations."
                                )
                            }
                            break
                        } else {
                            stateHolder = cur.copy(remainingSeconds = cur.remainingSeconds - 1)
                        }
                    }
                }

                PlushieSaveRoomScreen(
                    uiState = uiState,
                    terminalLines = terminalLog,
                    workDir = filesDir,
                    onToggleTimer = {
                        if (stateHolder.isTimerRunning) {
                            stopContainmentService()
                            updateAndPersist {
                                it.copy(isTimerRunning = false, bannerMessage = "Save Room timer paused.")
                            }
                        } else {
                            startContainmentService()
                            updateAndPersist {
                                it.copy(
                                    isTimerRunning = true,
                                    remainingSeconds = if (it.remainingSeconds <= 0) it.pomodoroMinutes * 60 else it.remainingSeconds,
                                    bannerMessage = "Bio-Shield ON: ${it.pomodoroMinutes}m study lock armed."
                                )
                            }
                        }
                    },
                    onCycleFocusPreset = {
                        val presets = listOf(15, 25, 50, 64)
                        val idx = presets.indexOf(stateHolder.pomodoroMinutes)
                        val nextMins = presets[(idx + 1) % presets.size]
                        val mcToast = if (nextMins == 64) "Minecraft 64-Stack Pomodoro unlocked!" else null
                        updateAndPersist {
                            it.copy(
                                pomodoroMinutes = nextMins,
                                remainingSeconds = nextMins * 60,
                                isTimerRunning = false,
                                bannerMessage = "Focus block set to ${nextMins} minutes.",
                                easterEggToast = mcToast
                            )
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
                                it.copy(bannerMessage = "Out of First Aid Sprays! Stay in the Save Room.")
                            }
                        }
                    },
                    onSimulateIgMinute = {
                        updateAndPersist {
                            val nextIg = it.instagramMinutesToday + 5
                            it.copy(
                                instagramMinutesToday = nextIg,
                                bannerMessage = "Logged +5m Instagram time (${nextIg}m today)."
                            )
                        }
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
                            if (shouldStart) startContainmentService()
                            cur.copy(
                                pomodoroMinutes = newMins,
                                remainingSeconds = if (shouldStart) newMins * 60 else cur.remainingSeconds,
                                isTimerRunning = if (shouldStart) true else cur.isTimerRunning,
                                shinyAxolotlUnlocked = cur.shinyAxolotlUnlocked || res.unlockShinyAxolotl,
                                shinyCount = if (res.unlockShinyAxolotl) cur.shinyCount + 1 else cur.shinyCount,
                                terminalThemeActive = if (res.toggleTermTheme) !cur.terminalThemeActive else cur.terminalThemeActive,
                                herbPoints = if (res.mixHerbs) cur.herbPoints + 10 else cur.herbPoints,
                                easterEggToast = when {
                                    res.unlockShinyAxolotl -> "Specimen #AX-01 Shiny Blue Axolotl summoned!"
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

    override fun onResume() {
        super.onResume()
        sensorRig?.start()
        stateHolder = stateHolder.copy(
            usageAccessGranted = ContainmentService.hasUsageStatsPermission(this),
            overlayPermissionGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this),
            termuxInstalled = TerminalEngine.isTermuxInstalled(this)
        )
    }

    override fun onPause() {
        super.onPause()
        sensorRig?.stop()
    }

    private fun startContainmentService() {
        val intent = Intent(this, ContainmentService::class.java).apply {
            action = ContainmentService.ACTION_START_LOCK
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
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

@Composable
private fun PlushieSaveRoomScreen(
    uiState: PlushieUiState,
    terminalLines: List<String>,
    workDir: File,
    onToggleTimer: () -> Unit,
    onCycleFocusPreset: () -> Unit,
    onUseFirstAidSpray: () -> Unit,
    onSimulateIgMinute: () -> Unit,
    onTypewriterTap: () -> Unit,
    onOpenUsageSettings: () -> Unit,
    onOpenOverlaySettings: () -> Unit,
    onRunShellCommand: (String) -> Unit
) {
    var cmdInput by remember { mutableStateOf("") }
    val mins = uiState.remainingSeconds / 60
    val secs = uiState.remainingSeconds % 60
    val formattedClock = String.format("%02d:%02d", mins, secs)

    val herbColor = when {
        uiState.instagramMinutesToday >= 45 -> HerbRed
        uiState.instagramMinutesToday >= 20 -> HerbYellow
        else -> HerbGreen
    }

    val shinyBrush = Brush.horizontalGradient(
        colors = listOf(ShinyAxolotlCyan, Color(0xFFA855F7), Color(0xFFF472B6), ShinyAxolotlCyan)
    )

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = if (uiState.lowLightNightOps) Color(0xFF120D05) else MaterialTheme.colorScheme.background
    ) {
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    border = BorderStroke(
                        1.dp,
                        if (uiState.shinyAxolotlUnlocked) ShinyAxolotlCyan else herbColor
                    )
                ) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Text(
                            text = if (uiState.shinyAxolotlUnlocked) {
                                "SAVE ROOM PLUSHIE + SHINY AXOLOTL (#AX-01)"
                            } else {
                                "SAVE ROOM PLUSHIE — BIOHAZARD CONTAINMENT"
                            },
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = if (uiState.shinyAxolotlUnlocked) ShinyAxolotlCyan else herbColor
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = uiState.bannerMessage,
                            style = MaterialTheme.typography.bodySmall,
                            color = if (uiState.lowLightNightOps) AmberNightOps else MaterialTheme.colorScheme.onSurface
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            text = "Vitality: ${uiState.herbStatus} | IG: ${uiState.instagramMinutesToday}m | Herbs: ${uiState.herbPoints} | Sprays: ${uiState.firstAidSpraysLeft}",
                            style = MaterialTheme.typography.labelSmall,
                            color = herbColor
                        )
                        Text(
                            text = "Sensors: Stealth=${if (uiState.stealthFaceDown) "ON" else "OFF"} | NightOps=${if (uiState.lowLightNightOps) "ON" else "OFF"} | Tilt=(${"%.1f".format(uiState.tiltX)}, ${"%.1f".format(uiState.tiltY)})",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.75f)
                        )
                        uiState.easterEggToast?.let { egg ->
                            Spacer(modifier = Modifier.height(6.dp))
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
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

            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Text(
                            text = "POMODORO SAFE ROOM: $formattedClock (${uiState.pomodoroMinutes}m block)",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = onToggleTimer) {
                                Text(if (uiState.isTimerRunning) "Pause Shield" else "Start Save Room")
                            }
                            OutlinedButton(onClick = onCycleFocusPreset) {
                                Text("Preset (${uiState.pomodoroMinutes}m)")
                            }
                        }
                        Spacer(modifier = Modifier.height(6.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = onUseFirstAidSpray) {
                                Text("First Aid Spray (${uiState.firstAidSpraysLeft})")
                            }
                            OutlinedButton(onClick = onSimulateIgMinute) {
                                Text("+5m IG Log")
                            }
                            OutlinedButton(onClick = onTypewriterTap) {
                                Text(if (uiState.crtScanlinesEnabled) "CRT: ON" else "Typewriter CRT")
                            }
                        }
                        if (!uiState.usageAccessGranted || !uiState.overlayPermissionGranted) {
                            Spacer(modifier = Modifier.height(6.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
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
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Text(
                            text = "LIVE SHELL + TERMUX BRIDGE (${if (uiState.termuxInstalled) "Termux Found" else "Built-in sh"})",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            OutlinedTextField(
                                value = cmdInput,
                                onValueChange = { cmdInput = it },
                                modifier = Modifier.weight(1f),
                                singleLine = true,
                                placeholder = { Text("saferoom 25 / spawn axolotl / ls") }
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
                                .background(Color(0xFF050806))
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

            item {
                Text(
                    text = "ATTACHE CASE STASH (SHINY & FOCUS ITEMS)",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
            }

            items(uiState.stashItems, key = { it.id }) { item ->
                StashItemCard(entry = item)
            }
        }
    }
}

@Composable
private fun StashItemCard(entry: StashEntry) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { },
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, if (entry.shiny) ShinyAxolotlCyan else Color(0xFF26362E))
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = entry.title,
                    fontWeight = FontWeight.SemiBold,
                    color = if (entry.shiny) ShinyAxolotlCyan else MaterialTheme.colorScheme.onSurface
                )
                Text(
                    text = entry.category,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                )
            }
            if (entry.shiny) {
                Text(
                    text = "SHINY FOIL",
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                    color = ShinyAxolotlCyan
                )
            }
        }
    }
}

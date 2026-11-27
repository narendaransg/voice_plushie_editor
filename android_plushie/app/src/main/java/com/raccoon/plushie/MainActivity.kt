package com.raccoon.plushie

import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Process
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.raccoon.plushie.audio.SaveRoomSoundEffects
import com.raccoon.plushie.data.Biome
import com.raccoon.plushie.data.CompletedEventRecord
import com.raccoon.plushie.data.ForestPlot
import com.raccoon.plushie.data.PlushieState
import com.raccoon.plushie.data.PlushieStorage
import com.raccoon.plushie.data.ProgressionCatalog
import com.raccoon.plushie.data.SanctuaryMode
import com.raccoon.plushie.data.TodoItem
import com.raccoon.plushie.data.TreeSpecies
import com.raccoon.plushie.overlay.LeonOverlayService
import com.raccoon.plushie.service.ContainmentService
import com.raccoon.plushie.poster.RemotePosterRepository
import com.raccoon.plushie.poster.SaveRoomPoster
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private enum class AppSection(val title: String) {
    HOME("Save Room"),
    SANCTUARY("Pet & Forest"),
    LEVELS("20-Lv Loop"),
    REELS_FRIENDS("Reels & Friends"),
    HISTORY("History"),
    SETTINGS("Settings & Perms")
}

private val SaveRoomDarkScheme = darkColorScheme(
    primary = Color(0xFF39D98A),
    onPrimary = Color(0xFF07130D),
    secondary = Color(0xFFE5B54B),
    onSecondary = Color(0xFF1A1404),
    background = Color(0xFF0B100E),
    onBackground = Color(0xFFEAF3EE),
    surface = Color(0xFF131C18),
    onSurface = Color(0xFFEAF3EE),
    surfaceVariant = Color(0xFF1C2822),
    onSurfaceVariant = Color(0xFFB5C7BE),
    error = Color(0xFFFF5C6C)
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = SaveRoomDarkScheme) {
                SaveRoomApp()
            }
        }
    }
}

private fun hasUsageAccess(context: Context): Boolean {
    return runCatching {
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as? AppOpsManager ?: return@runCatching false
        @Suppress("DEPRECATION")
        val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            appOps.unsafeCheckOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS,
                Process.myUid(),
                context.packageName
            )
        } else {
            appOps.checkOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS,
                Process.myUid(),
                context.packageName
            )
        }
        if (mode == AppOpsManager.MODE_ALLOWED) return@runCatching true
        if (mode == AppOpsManager.MODE_DEFAULT) {
            val usm = context.getSystemService(Context.USAGE_STATS_SERVICE) as? android.app.usage.UsageStatsManager
            val now = System.currentTimeMillis()
            val stats = usm?.queryUsageStats(android.app.usage.UsageStatsManager.INTERVAL_DAILY, now - 86_400_000L, now)
            return@runCatching !stats.isNullOrEmpty()
        }
        false
    }.getOrDefault(false)
}

private fun nowTimeLabel(): String =
    SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())

@Composable
private fun drawableIdOrZero(context: Context, name: String): Int =
    context.resources.getIdentifier(name, "drawable", context.packageName)

@Composable
private fun PetSpriteFrame(
    petPrefix: String,
    stage: Int,
    moodHappy: Boolean,
    breach: Boolean,
    animTick: Int,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val candidates = remember(petPrefix, stage, moodHappy, breach, animTick) {
        if (breach) {
            listOf("${petPrefix}_breach_${((animTick % 3) + 1).toString().padStart(2, '0')}", "${petPrefix}_breach_01")
        } else {
            val moodIdx = if (moodHappy) 2 else 1
            val evoFrame = ((stage.coerceIn(1, 3) - 1) * 3) + moodIdx
            val moveFrame = ((stage.coerceIn(1, 3) - 1) * 2) + ((animTick % 2) + 1)
            listOf(
                "${petPrefix}_evo_${evoFrame.toString().padStart(2, '0')}",
                "${petPrefix}_move_${moveFrame.toString().padStart(2, '0')}",
                "${petPrefix}_evo_01"
            )
        }
    }
    val resId = candidates.firstNotNullOfOrNull { name ->
        drawableIdOrZero(context, name).takeIf { it != 0 }
    } ?: 0

    if (resId != 0) {
        Image(
            painter = painterResource(resId),
            contentDescription = null,
            contentScale = ContentScale.Fit,
            modifier = modifier
        )
    } else {
        Box(
            modifier = modifier.background(Color(0xFF1D2C25), RoundedCornerShape(12.dp)),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = if (breach) "!" else "St.$stage",
                color = if (breach) Color(0xFFFF5C6C) else Color(0xFF39D98A),
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
private fun TreeSpriteFrame(
    plot: ForestPlot,
    breach: Boolean,
    animTick: Int,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val prefix = plot.species.prefix
    val stage = plot.stage
    val candidates = remember(prefix, stage, breach, animTick) {
        if (breach) {
            listOf("${prefix}_breach_${((animTick % 3) + 1).toString().padStart(2, '0')}", "${prefix}_breach_01")
        } else {
            val animFrame = ((stage.coerceIn(1, 4) - 1) * 2).coerceAtMost(4) + ((animTick % 2) + 1)
            listOf(
                "${prefix}_growth_${stage.coerceIn(1, 4).toString().padStart(2, '0')}",
                "${prefix}_anim_${animFrame.toString().padStart(2, '0')}",
                "${prefix}_growth_01"
            )
        }
    }
    val resId = candidates.firstNotNullOfOrNull { name ->
        drawableIdOrZero(context, name).takeIf { it != 0 }
    } ?: 0

    if (resId != 0) {
        Image(
            painter = painterResource(resId),
            contentDescription = null,
            contentScale = ContentScale.Fit,
            modifier = modifier
        )
    } else {
        Box(
            modifier = modifier.background(Color(0xFF1A2A22), RoundedCornerShape(12.dp)),
            contentAlignment = Alignment.Center
        ) {
            Text("Lv${plot.stage}", color = Color(0xFF39D98A), fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun HabitatBackdrop(
    mode: SanctuaryMode,
    biome: Biome,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val resName = when (mode) {
        SanctuaryMode.FOREST -> "bg_forest_day_meadow"
        SanctuaryMode.PET_ROOM -> when (biome) {
            Biome.WATER -> "bg_habitat_water_tank"
            Biome.AIR -> "bg_habitat_air_roost"
            Biome.LAND -> "bg_habitat_land_terrarium"
        }
    }
    val resId = drawableIdOrZero(context, resName)
    Box(
        modifier = modifier.background(Color(0xFF0E1613), RoundedCornerShape(14.dp)),
        contentAlignment = Alignment.Center
    ) {
        if (resId != 0) {
            Image(
                painter = painterResource(resId),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize()
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SaveRoomApp() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }
    val soundEffects = remember { SaveRoomSoundEffects(context) }

    var state by remember { mutableStateOf(PlushieStorage.load(context)) }
    var section by remember { mutableStateOf(AppSection.HOME) }
    val drawerState = rememberDrawerState(DrawerValue.Closed)

    var timerRunning by remember { mutableStateOf(false) }
    var remainingSeconds by remember { mutableIntStateOf(25 * 60) }
    var animTick by remember { mutableIntStateOf(0) }
    var newTaskTitle by remember { mutableStateOf("") }
    var petNameDraft by remember(state.activePetId, state.petCustomNames) {
        val currentPet = ProgressionCatalog.allPets.firstOrNull { it.id == state.activePetId }
        mutableStateOf(currentPet?.let { state.petCustomNames[it.id].orEmpty() } ?: "")
    }

    var overlayGranted by remember { mutableStateOf(Settings.canDrawOverlays(context)) }
    var usageGranted by remember { mutableStateOf(hasUsageAccess(context)) }

    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                overlayGranted = Settings.canDrawOverlays(context)
                usageGranted = hasUsageAccess(context)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    DisposableEffect(Unit) {
        onDispose { soundEffects.release() }
    }

    fun updateState(transform: (PlushieState) -> PlushieState) {
        val updated = transform(state)
        state = updated
        PlushieStorage.save(context, updated)
    }

    fun setOverlayOptIn(enabled: Boolean) {
        if (enabled && !Settings.canDrawOverlays(context)) {
            updateState { it.copy(overlayEnabled = false) }
            context.startActivity(
                Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:${context.packageName}")
                ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
            return
        }
        updateState { it.copy(overlayEnabled = enabled) }
        val intent = Intent(context, LeonOverlayService::class.java)
        if (enabled) context.startService(intent) else context.stopService(intent)
    }

    fun completeFocusSession(minutes: Int) {
        val bonus = state.prestigeCycle * 25
        val earned = (minutes * 2) + bonus
        val record = CompletedEventRecord(
            id = "ev-${System.currentTimeMillis()}",
            label = "Focus Block (${minutes}m)",
            fpEarned = earned,
            timestampLabel = nowTimeLabel()
        )
        updateState { s ->
            val updatedPlots = if (s.forestPlots.isNotEmpty()) {
                val first = s.forestPlots.first().copy(sessionsCompleted = s.forestPlots.first().sessionsCompleted + 1)
                listOf(first) + s.forestPlots.drop(1)
            } else s.forestPlots
            s.copy(
                focusPoints = s.focusPoints + earned,
                completedFocusSessions = s.completedFocusSessions + 1,
                levelFocusDone = true,
                breachAlertActive = false,
                forestPlots = updatedPlots,
                history = listOf(record) + s.history
            )
        }
        soundEffects.playHerbChime()
        scope.launch {
            snackbarHostState.showSnackbar("Session logged: +$earned FP")
        }
    }

    LaunchedEffect(timerRunning) {
        while (timerRunning) {
            delay(1000L)
            if (remainingSeconds > 1) {
                remainingSeconds -= 1
            } else {
                timerRunning = false
                remainingSeconds = 25 * 60
                completeFocusSession(25)
            }
        }
    }

    LaunchedEffect(Unit) {
        while (true) {
            delay(650L)
            animTick += 1
        }
    }

    if (!state.doorUnlocked) {
        EntryGateScreen(
            operatorName = state.operatorName,
            onNameChange = { name -> updateState { it.copy(operatorName = name) } },
            onEnter = {
                updateState { it.copy(doorUnlocked = true, overlayEnabled = false) }
                soundEffects.playOpeningPunchline(state.voiceTtsEnabled)
            }
        )
        return
    }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet(drawerContainerColor = Color(0xFF121B17)) {
                Text(
                    text = "SAVE ROOM PLUSHIE",
                    color = Color(0xFF39D98A),
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(16.dp)
                )
                Text(
                    text = "${state.operatorName} • ${ProgressionCatalog.prestigeBadge(state.sanctuaryLevel)} • ${state.focusPoints} FP",
                    color = Color(0xFFB5C7BE),
                    fontSize = 13.sp,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                )
                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                AppSection.entries.forEach { dest ->
                    val selected = dest == section
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(if (selected) Color(0xFF1F3329) else Color.Transparent)
                            .clickable {
                                soundEffects.playUiTap()
                                section = dest
                                scope.launch { drawerState.close() }
                            }
                            .padding(horizontal = 16.dp, vertical = 14.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = dest.title,
                            color = if (selected) Color(0xFF39D98A) else Color(0xFFEAF3EE),
                            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal
                        )
                    }
                }
            }
        }
    ) {
        Scaffold(
            containerColor = Color(0xFF0B100E),
            snackbarHost = { SnackbarHost(snackbarHostState) },
            topBar = {
                TopAppBar(
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = Color(0xFF111915)),
                    navigationIcon = {
                        IconButton(onClick = {
                            soundEffects.playUiTap()
                            scope.launch { drawerState.open() }
                        }) {
                            Icon(Icons.Default.Menu, contentDescription = "Menu", tint = Color(0xFFEAF3EE))
                        }
                    },
                    title = {
                        Text(
                            text = "${section.title} • ${ProgressionCatalog.prestigeBadge(state.sanctuaryLevel)}",
                            fontSize = 17.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = Color(0xFFEAF3EE)
                        )
                    },
                    actions = {
                        Text(
                            text = "${state.focusPoints} FP",
                            color = Color(0xFFE5B54B),
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(end = 14.dp)
                        )
                    }
                )
            }
        ) { innerPadding ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
            ) {
                when (section) {
                    AppSection.HOME -> MinimalHomeScreen(
                        state = state,
                        remainingSeconds = remainingSeconds,
                        timerRunning = timerRunning,
                        animTick = animTick,
                        newTaskTitle = newTaskTitle,
                        onNewTaskChange = { newTaskTitle = it },
                        onToggleTimer = {
                            soundEffects.playUiTap()
                            timerRunning = !timerRunning
                        },
                        onCompleteNow = {
                            timerRunning = false
                            remainingSeconds = 25 * 60
                            completeFocusSession(25)
                        },
                        onOpenSanctuary = {
                            soundEffects.playUiTap()
                            section = AppSection.SANCTUARY
                        },
                        onAddTask = {
                            val clean = newTaskTitle.trim()
                            if (clean.isNotEmpty()) {
                                updateState { s ->
                                    s.copy(tasks = s.tasks + TodoItem("t-${System.currentTimeMillis()}", clean, false))
                                }
                                newTaskTitle = ""
                                soundEffects.playTypewriterSave()
                            }
                        },
                        onToggleTask = { item ->
                            val nowDone = !item.done
                            updateState { s ->
                                val nextTasks = s.tasks.map { if (it.id == item.id) it.copy(done = nowDone) else it }
                                val nextHistory = if (nowDone) {
                                    listOf(
                                        CompletedEventRecord(
                                            id = "ev-${System.currentTimeMillis()}",
                                            label = "Task: ${item.title}",
                                            fpEarned = 15,
                                            timestampLabel = nowTimeLabel()
                                        )
                                    ) + s.history
                                } else s.history
                                s.copy(
                                    tasks = nextTasks,
                                    focusPoints = if (nowDone) s.focusPoints + 15 else s.focusPoints,
                                    completedTasksCount = if (nowDone) s.completedTasksCount + 1 else s.completedTasksCount,
                                    history = nextHistory
                                )
                            }
                            if (nowDone) soundEffects.playTypewriterSave()
                        },
                        onRemoveTask = { target ->
                            val idx = state.tasks.indexOfFirst { it.id == target.id }
                            if (idx >= 0) {
                                updateState { s -> s.copy(tasks = s.tasks.filterNot { it.id == target.id }) }
                                soundEffects.playUiTap()
                                scope.launch {
                                    val res = snackbarHostState.showSnackbar(
                                        message = "Removed: ${target.title}",
                                        actionLabel = "Undo",
                                        duration = SnackbarDuration.Short
                                    )
                                    if (res == SnackbarResult.ActionPerformed) {
                                        updateState { s ->
                                            val list = s.tasks.toMutableList()
                                            list.add(idx.coerceIn(0, list.size), target)
                                            s.copy(tasks = list)
                                        }
                                    }
                                }
                            }
                        }
                    )

                    AppSection.SANCTUARY -> SanctuaryScreen(
                        state = state,
                        animTick = animTick,
                        petNameDraft = petNameDraft,
                        onPetNameDraftChange = { petNameDraft = it },
                        onSwitchMode = { mode ->
                            soundEffects.playUiTap()
                            updateState { it.copy(sanctuaryMode = mode) }
                        },
                        onSelectBiome = { biome ->
                            soundEffects.playUiTap()
                            val firstInBiome = ProgressionCatalog.allPets.firstOrNull { it.biome == biome }
                            updateState { s ->
                                s.copy(
                                    activeBiome = biome,
                                    activePetId = if (firstInBiome != null && firstInBiome.id in s.unlockedPetIds) firstInBiome.id else s.activePetId
                                )
                            }
                        },
                        onSelectOrUnlockPet = { pet ->
                            if (pet.id in state.unlockedPetIds) {
                                soundEffects.playUiTap()
                                updateState { it.copy(activePetId = pet.id, activeBiome = pet.biome) }
                            } else if (state.unlockedPetIds.size < state.maxPetSlots && state.focusPoints >= pet.unlockCostFp) {
                                soundEffects.playHerbChime()
                                val ev = CompletedEventRecord(
                                    id = "ev-${System.currentTimeMillis()}",
                                    label = "Unlocked ${pet.name}",
                                    fpEarned = 0,
                                    timestampLabel = nowTimeLabel()
                                )
                                updateState { s ->
                                    s.copy(
                                        focusPoints = s.focusPoints - pet.unlockCostFp,
                                        unlockedPetIds = s.unlockedPetIds + pet.id,
                                        activePetId = pet.id,
                                        activeBiome = pet.biome,
                                        history = listOf(ev) + s.history
                                    )
                                }
                            }
                        },
                        onSavePetName = { petId ->
                            if (state.canNamePets) {
                                updateState { s ->
                                    val map = s.petCustomNames.toMutableMap()
                                    val clean = petNameDraft.trim()
                                    if (clean.isEmpty()) map.remove(petId) else map[petId] = clean
                                    s.copy(petCustomNames = map)
                                }
                                soundEffects.playTypewriterSave()
                            }
                        },
                        onPlantTree = { species ->
                            val cost = 60
                            if (state.focusPoints >= cost) {
                                soundEffects.playTreeGrow()
                                val ev = CompletedEventRecord(
                                    id = "ev-${System.currentTimeMillis()}",
                                    label = "Planted ${species.displayName}",
                                    fpEarned = 0,
                                    timestampLabel = nowTimeLabel()
                                )
                                updateState { s ->
                                    s.copy(
                                        focusPoints = s.focusPoints - cost,
                                        forestPlots = s.forestPlots + ForestPlot("plot-${System.currentTimeMillis()}", species, 1),
                                        history = listOf(ev) + s.history
                                    )
                                }
                            }
                        },
                        onNurturePlot = { plotId ->
                            val cost = 35
                            if (state.focusPoints >= cost) {
                                soundEffects.playTreeGrow()
                                updateState { s ->
                                    s.copy(
                                        focusPoints = s.focusPoints - cost,
                                        forestPlots = s.forestPlots.map {
                                            if (it.id == plotId) it.copy(sessionsCompleted = it.sessionsCompleted + 1) else it
                                        }
                                    )
                                }
                            }
                        }
                    )

                    AppSection.LEVELS -> LevelsLoopScreen(
                        state = state,
                        onToggleOutdoorTask = {
                            soundEffects.playTypewriterSave()
                            updateState { it.copy(levelOutdoorDone = !it.levelOutdoorDone) }
                        },
                        onCompleteLevel = {
                            val tpl = ProgressionCatalog.templateForLevel(state.sanctuaryLevel)
                            val reward = tpl.baseFpReward + (state.prestigeCycle * 50)
                            val completedLv = state.sanctuaryLevel
                            val nextLv = completedLv + 1
                            val ev = CompletedEventRecord(
                                id = "ev-${System.currentTimeMillis()}",
                                label = "Completed Lv.$completedLv (${tpl.title})",
                                fpEarned = reward,
                                timestampLabel = nowTimeLabel()
                            )
                            updateState { s ->
                                s.copy(
                                    sanctuaryLevel = nextLv,
                                    focusPoints = s.focusPoints + reward,
                                    levelFocusDone = false,
                                    levelOutdoorDone = false,
                                    history = listOf(ev) + s.history
                                )
                            }
                            soundEffects.playLevelUp()
                            scope.launch {
                                snackbarHostState.showSnackbar("Level $completedLv complete! +$reward FP -> ${ProgressionCatalog.prestigeBadge(nextLv)}")
                            }
                        }
                    )

                    AppSection.REELS_FRIENDS -> ReelsAndFriendsScreen(
                        state = state,
                        onLogReel = { delta ->
                            val nextCount = (state.dailyReelsWatched + delta).coerceAtLeast(0)
                            val overCap = nextCount > state.dailyReelsCap
                            if (overCap && delta > 0) soundEffects.playShieldAlert() else soundEffects.playUiTap()
                            updateState { it.copy(dailyReelsWatched = nextCount, breachAlertActive = overCap) }
                        },
                        onResetReels = {
                            soundEffects.playHerbChime()
                            updateState { it.copy(dailyReelsWatched = 0, breachAlertActive = false) }
                        },
                        onChangeCap = { delta ->
                            updateState { it.copy(dailyReelsCap = (it.dailyReelsCap + delta).coerceIn(5, 80)) }
                        }
                    )

                    AppSection.HISTORY -> HistoryScreen(
                        history = state.history,
                        onClearHistory = {
                            soundEffects.playUiTap()
                            updateState { it.copy(history = emptyList()) }
                        }
                    )

                    AppSection.SETTINGS -> SettingsAndPermissionsScreen(
                        state = state,
                        overlayGranted = overlayGranted,
                        usageGranted = usageGranted,
                        onToggleOverlay = { setOverlayOptIn(it) },
                        onToggleCrt = { updateState { s -> s.copy(crtScanlinesEnabled = !s.crtScanlinesEnabled) } },
                        onToggleVoice = { updateState { s -> s.copy(voiceTtsEnabled = !s.voiceTtsEnabled) } },
                        onTestSound = { soundEffects.playOpeningPunchline(state.voiceTtsEnabled) },
                        onOpenAppSettings = {
                            context.startActivity(
                                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                                    .setData(Uri.parse("package:${context.packageName}"))
                                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            )
                        },
                        onOpenOverlaySettings = {
                            context.startActivity(
                                Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION)
                                    .setData(Uri.parse("package:${context.packageName}"))
                                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            )
                        },
                        onOpenUsageSettings = {
                            context.startActivity(
                                Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)
                                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            )
                        },
                        onStartContainment = {
                            if (hasUsageAccess(context)) {
                                context.startService(Intent(context, ContainmentService::class.java))
                                soundEffects.playTypewriterSave()
                            } else {
                                context.startActivity(
                                    Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)
                                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                )
                            }
                        }
                    )
                }

                if (state.crtScanlinesEnabled) {
                    Canvas(modifier = Modifier.fillMaxSize()) {
                        var y = 0f
                        while (y < size.height) {
                            drawLine(
                                color = Color(0x12FFFFFF),
                                start = Offset(0f, y),
                                end = Offset(size.width, y),
                                strokeWidth = 1.5f
                            )
                            y += 8f
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EntryGateScreen(
    operatorName: String,
    onNameChange: (String) -> Unit,
    onEnter: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0B100E))
            .padding(24.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Text("SAVE ROOM PLUSHIE", color = Color(0xFF39D98A), fontSize = 24.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text(
            "Minimalist focus sanctuary. Zero overlays on start.",
            color = Color(0xFFB5C7BE),
            fontSize = 14.sp
        )
        Spacer(Modifier.height(20.dp))
        OutlinedTextField(
            value = operatorName,
            onValueChange = onNameChange,
            label = { Text("Your Name") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = onEnter,
            modifier = Modifier.fillMaxWidth().height(48.dp)
        ) {
            Text("Enter Save Room")
        }
    }
}

@Composable
private fun MinimalHomeScreen(
    state: PlushieState,
    remainingSeconds: Int,
    timerRunning: Boolean,
    animTick: Int,
    newTaskTitle: String,
    onNewTaskChange: (String) -> Unit,
    onToggleTimer: () -> Unit,
    onCompleteNow: () -> Unit,
    onOpenSanctuary: () -> Unit,
    onAddTask: () -> Unit,
    onToggleTask: (TodoItem) -> Unit,
    onRemoveTask: (TodoItem) -> Unit
) {
    val activePet = ProgressionCatalog.allPets.firstOrNull { it.id == state.activePetId }
        ?: ProgressionCatalog.allPets.first()
    val mins = remainingSeconds / 60
    val secs = remainingSeconds % 60

    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
        modifier = Modifier.fillMaxSize()
    ) {
        item {
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF131C18))) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(18.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}",
                        fontSize = 44.sp,
                        fontWeight = FontWeight.Bold,
                        color = if (state.breachAlertActive) Color(0xFFFF5C6C) else Color(0xFF39D98A)
                    )
                    Spacer(Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Button(onClick = onToggleTimer) {
                            Text(if (timerRunning) "Pause" else "Start Focus")
                        }
                        OutlinedButton(onClick = onCompleteNow) {
                            Text("Finish Block")
                        }
                    }
                }
            }
        }

        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFF131C18)),
                modifier = Modifier.fillMaxWidth().clickable { onOpenSanctuary() }
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = if (state.sanctuaryMode == SanctuaryMode.FOREST) "Forest Grove" else state.petDisplayName(activePet),
                            fontWeight = FontWeight.Bold,
                            fontSize = 17.sp,
                            color = Color(0xFFEAF3EE)
                        )
                        Text(
                            text = if (state.sanctuaryMode == SanctuaryMode.FOREST)
                                "${state.forestPlots.size} plot(s) • Tap to open"
                            else
                                "${activePet.biome.label} • Stage ${state.petGrowthStage(activePet)} • Tap to open",
                            color = Color(0xFFB5C7BE),
                            fontSize = 13.sp
                        )
                    }
                    Box(modifier = Modifier.size(76.dp), contentAlignment = Alignment.Center) {
                        if (state.sanctuaryMode == SanctuaryMode.FOREST && state.forestPlots.isNotEmpty()) {
                            TreeSpriteFrame(
                                plot = state.forestPlots.first(),
                                breach = state.breachAlertActive,
                                animTick = animTick,
                                modifier = Modifier.fillMaxSize()
                            )
                        } else {
                            PetSpriteFrame(
                                petPrefix = activePet.prefix,
                                stage = state.petGrowthStage(activePet),
                                moodHappy = !state.breachAlertActive && state.levelFocusDone,
                                breach = state.breachAlertActive,
                                animTick = animTick,
                                modifier = Modifier.fillMaxSize()
                            )
                        }
                    }
                }
            }
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = newTaskTitle,
                    onValueChange = onNewTaskChange,
                    placeholder = { Text("Add a task...") },
                    singleLine = true,
                    modifier = Modifier.weight(1f)
                )
                Button(onClick = onAddTask) { Text("Add") }
            }
        }

        items(state.tasks, key = { it.id }) { item ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Color(0xFF131C18), RoundedCornerShape(10.dp))
                    .border(1.dp, Color(0xFF22332B), RoundedCornerShape(10.dp))
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = if (item.done) "[x]" else "[ ]",
                    color = if (item.done) Color(0xFF39D98A) else Color(0xFFB5C7BE),
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.clickable { onToggleTask(item) }.padding(end = 10.dp)
                )
                Text(
                    text = item.title,
                    color = if (item.done) Color(0xFF7D9389) else Color(0xFFEAF3EE),
                    textDecoration = if (item.done) TextDecoration.LineThrough else TextDecoration.None,
                    modifier = Modifier.weight(1f).clickable { onToggleTask(item) }
                )
                IconButton(onClick = { onRemoveTask(item) }) {
                    Icon(
                        imageVector = Icons.Default.Delete,
                        contentDescription = "Remove task",
                        tint = Color(0xFF9FB4AA)
                    )
                }
            }
        }
    }
}

@Composable
private fun SanctuaryScreen(
    state: PlushieState,
    animTick: Int,
    petNameDraft: String,
    onPetNameDraftChange: (String) -> Unit,
    onSwitchMode: (SanctuaryMode) -> Unit,
    onSelectBiome: (Biome) -> Unit,
    onSelectOrUnlockPet: (com.raccoon.plushie.data.PetSpec) -> Unit,
    onSavePetName: (String) -> Unit,
    onPlantTree: (TreeSpecies) -> Unit,
    onNurturePlot: (String) -> Unit
) {
    val activePet = ProgressionCatalog.allPets.firstOrNull { it.id == state.activePetId }
        ?: ProgressionCatalog.allPets.first()

    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
        modifier = Modifier.fillMaxSize()
    ) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                FilterChip(
                    selected = state.sanctuaryMode == SanctuaryMode.PET_ROOM,
                    onClick = { onSwitchMode(SanctuaryMode.PET_ROOM) },
                    label = { Text("Pet Room") }
                )
                FilterChip(
                    selected = state.sanctuaryMode == SanctuaryMode.FOREST,
                    onClick = { onSwitchMode(SanctuaryMode.FOREST) },
                    label = { Text("Forest Grove") }
                )
            }
        }

        if (state.sanctuaryMode == SanctuaryMode.PET_ROOM) {
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Biome.entries.forEach { b ->
                        FilterChip(
                            selected = state.activeBiome == b,
                            onClick = { onSelectBiome(b) },
                            label = { Text(b.label) }
                        )
                    }
                }
            }

            item {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF131C18))) {
                    Box(modifier = Modifier.fillMaxWidth().height(190.dp)) {
                        HabitatBackdrop(
                            mode = SanctuaryMode.PET_ROOM,
                            biome = state.activeBiome,
                            modifier = Modifier.fillMaxSize()
                        )
                        PetSpriteFrame(
                            petPrefix = activePet.prefix,
                            stage = state.petGrowthStage(activePet),
                            moodHappy = !state.breachAlertActive,
                            breach = state.breachAlertActive,
                            animTick = animTick,
                            modifier = Modifier.size(136.dp).align(Alignment.Center)
                        )
                    }
                    Column(modifier = Modifier.padding(14.dp)) {
                        Text(
                            text = "${state.petDisplayName(activePet)} (${activePet.biome.label} • Stage ${state.petGrowthStage(activePet)})",
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFFEAF3EE)
                        )
                        Text(
                            text = "Slots used: ${state.unlockedPetIds.size}/${state.maxPetSlots} • Naming: ${if (state.canNamePets) "Unlocked" else "Unlocks at Lv.2 or 150 FP"}",
                            color = Color(0xFFB5C7BE),
                            fontSize = 12.sp
                        )
                        if (state.canNamePets) {
                            Spacer(Modifier.height(8.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                                OutlinedTextField(
                                    value = petNameDraft,
                                    onValueChange = onPetNameDraftChange,
                                    label = { Text("Custom Name") },
                                    singleLine = true,
                                    modifier = Modifier.weight(1f)
                                )
                                Button(onClick = { onSavePetName(activePet.id) }) { Text("Save") }
                            }
                        }
                    }
                }
            }

            items(ProgressionCatalog.allPets.filter { it.biome == state.activeBiome }, key = { it.id }) { pet ->
                val owned = pet.id in state.unlockedPetIds
                val canAfford = !owned && state.focusPoints >= pet.unlockCostFp && state.unlockedPetIds.size < state.maxPetSlots
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(Color(0xFF131C18), RoundedCornerShape(10.dp))
                        .padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(state.petDisplayName(pet), fontWeight = FontWeight.SemiBold, color = Color(0xFFEAF3EE))
                        Text(
                            text = if (owned) "Unlocked" else "${pet.unlockCostFp} FP to unlock",
                            color = if (owned) Color(0xFF39D98A) else Color(0xFFE5B54B),
                            fontSize = 12.sp
                        )
                    }
                    Button(
                        onClick = { onSelectOrUnlockPet(pet) },
                        enabled = owned || canAfford
                    ) {
                        Text(if (pet.id == state.activePetId) "Active" else if (owned) "Select" else "Unlock")
                    }
                }
            }
        } else {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF131C18))) {
                    Box(modifier = Modifier.fillMaxWidth().height(180.dp)) {
                        HabitatBackdrop(
                            mode = SanctuaryMode.FOREST,
                            biome = state.activeBiome,
                            modifier = Modifier.fillMaxSize()
                        )
                        Row(
                            modifier = Modifier.align(Alignment.BottomCenter).padding(8.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            state.forestPlots.take(4).forEach { plot ->
                                TreeSpriteFrame(
                                    plot = plot,
                                    breach = state.breachAlertActive,
                                    animTick = animTick,
                                    modifier = Modifier.size(96.dp)
                                )
                            }
                        }
                    }
                }
            }

            item {
                Text("Plant New Tree (60 FP)", fontWeight = FontWeight.Bold, color = Color(0xFFEAF3EE))
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TreeSpecies.entries.take(2).forEach { sp ->
                        OutlinedButton(
                            onClick = { onPlantTree(sp) },
                            enabled = state.focusPoints >= 60,
                            modifier = Modifier.weight(1f)
                        ) { Text(sp.displayName.substringBefore(" "), maxLines = 1) }
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TreeSpecies.entries.drop(2).forEach { sp ->
                        OutlinedButton(
                            onClick = { onPlantTree(sp) },
                            enabled = state.focusPoints >= 60,
                            modifier = Modifier.weight(1f)
                        ) { Text(sp.displayName.substringBefore(" "), maxLines = 1) }
                    }
                }
            }

            items(state.forestPlots, key = { it.id }) { plot ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(Color(0xFF131C18), RoundedCornerShape(10.dp))
                        .padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text("${plot.species.displayName} • Stage ${plot.stage}/4", fontWeight = FontWeight.SemiBold, color = Color(0xFFEAF3EE))
                        Text("${plot.sessionsCompleted} focus session(s)", color = Color(0xFFB5C7BE), fontSize = 12.sp)
                    }
                    Button(
                        onClick = { onNurturePlot(plot.id) },
                        enabled = state.focusPoints >= 35
                    ) { Text("Grow (35 FP)") }
                }
            }
        }
    }
}

@Composable
private fun LevelsLoopScreen(
    state: PlushieState,
    onToggleOutdoorTask: () -> Unit,
    onCompleteLevel: () -> Unit
) {
    val tpl = ProgressionCatalog.templateForLevel(state.sanctuaryLevel)
    val reward = tpl.baseFpReward + (state.prestigeCycle * 50)
    val reelsOk = state.dailyReelsWatched <= state.dailyReelsCap
    val ready = state.levelFocusDone && state.levelOutdoorDone && reelsOk

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(
            text = "${ProgressionCatalog.prestigeBadge(state.sanctuaryLevel)} — ${tpl.title}",
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            color = Color(0xFF39D98A)
        )
        Text(
            text = "20-Level Template #${tpl.templateLevel}/20 • Loop Cycle ${state.prestigeCycle} • Reward: +$reward FP",
            color = Color(0xFFE5B54B),
            fontSize = 13.sp
        )

        Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF131C18))) {
            Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("1. Focus: ${tpl.focusGoalText} (${if (state.levelFocusDone) "Done" else "Complete a focus block on Home"})", color = Color(0xFFEAF3EE))
                Text("2. Reels Cap: ${state.dailyReelsWatched}/${state.dailyReelsCap} today (${if (reelsOk) "Within cap" else "Over cap"})", color = Color(0xFFEAF3EE))
                Row(
                    modifier = Modifier.fillMaxWidth().clickable { onToggleOutdoorTask() },
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = "3. Outdoor: ${tpl.outdoorGoalText}",
                        color = Color(0xFFEAF3EE),
                        modifier = Modifier.weight(1f)
                    )
                    Text(
                        text = if (state.levelOutdoorDone) "DONE" else "CHECK",
                        color = if (state.levelOutdoorDone) Color(0xFF39D98A) else Color(0xFFE5B54B),
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }

        Button(
            onClick = onCompleteLevel,
            enabled = ready,
            modifier = Modifier.fillMaxWidth().height(48.dp)
        ) {
            Text(if (ready) "Advance to Level ${state.sanctuaryLevel + 1} (+$reward FP)" else "Complete Steps Above to Advance")
        }
    }
}

@Composable
private fun ReelsAndFriendsScreen(
    state: PlushieState,
    onLogReel: (Int) -> Unit,
    onResetReels: () -> Unit,
    onChangeCap: (Int) -> Unit
) {
    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxSize()
    ) {
        item {
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF131C18))) {
                Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(
                        text = "Today's Reels Counter: ${state.dailyReelsWatched} / ${state.dailyReelsCap}",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = if (state.dailyReelsWatched > state.dailyReelsCap) Color(0xFFFF5C6C) else Color(0xFF39D98A)
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { onLogReel(1) }) { Text("+1 Reel") }
                        OutlinedButton(onClick = { onLogReel(5) }) { Text("+5 Reels") }
                        OutlinedButton(onClick = onResetReels) { Text("Reset") }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Daily Cap:", color = Color(0xFFB5C7BE))
                        OutlinedButton(onClick = { onChangeCap(-5) }) { Text("-5") }
                        OutlinedButton(onClick = { onChangeCap(5) }) { Text("+5") }
                    }
                }
            }
        }

        item {
            Text("Friends Low-Reel & Focus Pace", fontWeight = FontWeight.Bold, color = Color(0xFFEAF3EE))
        }

        items(state.friends) { peer ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Color(0xFF131C18), RoundedCornerShape(10.dp))
                    .padding(12.dp),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text("${peer.name} (Lv.${peer.level})", fontWeight = FontWeight.SemiBold, color = Color(0xFFEAF3EE))
                    Text("${peer.focusMinutesToday}m focus today", color = Color(0xFFB5C7BE), fontSize = 12.sp)
                }
                Text("${peer.dailyReels} Reels", color = Color(0xFFE5B54B), fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun HistoryScreen(
    history: List<CompletedEventRecord>,
    onClearHistory: () -> Unit
) {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("Completed Events (${history.size})", fontWeight = FontWeight.Bold, color = Color(0xFFEAF3EE))
            if (history.isNotEmpty()) {
                OutlinedButton(onClick = onClearHistory) { Text("Clear") }
            }
        }
        if (history.isEmpty()) {
            Text("No completed sessions or milestones logged yet.", color = Color(0xFFB5C7BE))
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(history, key = { it.id }) { ev ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(Color(0xFF131C18), RoundedCornerShape(10.dp))
                            .padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(ev.label, color = Color(0xFFEAF3EE), fontWeight = FontWeight.Medium)
                            Text(ev.timestampLabel, color = Color(0xFFB5C7BE), fontSize = 12.sp)
                        }
                        if (ev.fpEarned > 0) {
                            Text("+${ev.fpEarned} FP", color = Color(0xFF39D98A), fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AdminPosterFeedCard(
    onRefreshPoster: (String, String, String) -> Unit
) {
    val ctx = LocalContext.current
    var feedUrl by remember { mutableStateOf(RemotePosterRepository.getConfiguredUrl(ctx)) }
    var adminId by remember { mutableStateOf(RemotePosterRepository.getAdminId(ctx)) }
    var signingKey by remember { mutableStateOf(RemotePosterRepository.getSigningKey(ctx)) }
    Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF131C18))) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Admin Poster Feed", fontWeight = FontWeight.Bold, color = Color(0xFFEAF3EE), maxLines = 1, softWrap = false)
            OutlinedTextField(
                value = feedUrl,
                onValueChange = { next -> feedUrl = next },
                label = { Text("HTTPS Feed URL", maxLines = 1, softWrap = false) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = adminId,
                onValueChange = { next -> adminId = next },
                label = { Text("Admin ID", maxLines = 1, softWrap = false) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = signingKey,
                onValueChange = { next -> signingKey = next },
                label = { Text("Signing Key", maxLines = 1, softWrap = false) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Button(
                onClick = { onRefreshPoster(feedUrl, adminId, signingKey) },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Save & Sync Poster", maxLines = 1, softWrap = false)
            }
        }
    }
}

@Composable
private fun SettingsAndPermissionsScreen(
    state: PlushieState,
    overlayGranted: Boolean,
    usageGranted: Boolean,
    onToggleOverlay: (Boolean) -> Unit,
    onToggleCrt: () -> Unit,
    onToggleVoice: () -> Unit,
    onTestSound: () -> Unit,
    onOpenAppSettings: () -> Unit,
    onOpenOverlaySettings: () -> Unit,
    onOpenUsageSettings: () -> Unit,
    onStartContainment: () -> Unit,
    onRefreshPoster: (String, String, String) -> Unit = { _, _, _ -> }
) {
    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxSize()
    ) {
        item {
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF131C18))) {
                Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Minimalist & Audio Preferences", fontWeight = FontWeight.Bold, color = Color(0xFFEAF3EE))
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text("Opt-In Floating Overlay", color = Color(0xFFEAF3EE))
                        Switch(checked = state.overlayEnabled, onCheckedChange = onToggleOverlay)
                    }
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text("CRT Scanlines", color = Color(0xFFEAF3EE))
                        Switch(checked = state.crtScanlinesEnabled, onCheckedChange = { onToggleCrt() })
                    }
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text("Spoken TTS Intro", color = Color(0xFFEAF3EE))
                        Switch(checked = state.voiceTtsEnabled, onCheckedChange = { onToggleVoice() })
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = onTestSound) { Text("Test Sound") }
                        OutlinedButton(onClick = onStartContainment) { Text("Containment Check") }
                    }
                }
            }
        }

        item {
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF131C18))) {
                Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Android System Permissions", fontWeight = FontWeight.Bold, color = Color(0xFFEAF3EE))
                    Text("Display over other apps: ${if (overlayGranted) "Granted" else "Needs Action"}", color = Color(0xFFB5C7BE), fontSize = 13.sp)
                    Text("Usage access (focus & app tracking): ${if (usageGranted) "Granted" else "Needs Action"}", color = Color(0xFFB5C7BE), fontSize = 13.sp)
                    OutlinedButton(onClick = onOpenAppSettings, modifier = Modifier.fillMaxWidth()) {
                        Text("Open App Info Settings")
                    }
                    OutlinedButton(onClick = onOpenOverlaySettings, modifier = Modifier.fillMaxWidth()) {
                        Text("Open Display Over Other Apps Settings")
                    }
                    OutlinedButton(onClick = onOpenUsageSettings, modifier = Modifier.fillMaxWidth()) {
                        Text("Open Usage Access Settings")
                    }
                }
            }
        }
        item { AdminPosterFeedCard(onRefreshPoster = onRefreshPoster) }
    }
}

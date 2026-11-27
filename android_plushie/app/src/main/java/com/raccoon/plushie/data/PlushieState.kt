package com.raccoon.plushie.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

enum class SanctuaryMode { PET_ROOM, FOREST }
enum class Biome(val label: String) { WATER("Water"), AIR("Air"), LAND("Land") }
enum class TreeSpecies(val id: String, val displayName: String, val prefix: String) {
    BIRCH("birch", "Silver Birch", "tree_birch"),
    SAKURA("sakura", "Sakura Blossom", "tree_sakura"),
    PINE("pine", "Himalayan Pine", "tree_pine"),
    BAMBOO("bamboo", "Bamboo Cluster", "tree_bamboo")
}

data class PetSpec(
    val id: String,
    val name: String,
    val biome: Biome,
    val prefix: String,
    val unlockCostFp: Int
)

data class TodoItem(
    val id: String,
    val title: String,
    val done: Boolean = false
)

data class CompletedEventRecord(
    val id: String,
    val label: String,
    val fpEarned: Int,
    val timestampLabel: String
)

data class ForestPlot(
    val id: String,
    val species: TreeSpecies,
    val sessionsCompleted: Int = 1
) {
    val stage: Int
        get() = when {
            sessionsCompleted >= 6 -> 4
            sessionsCompleted >= 4 -> 3
            sessionsCompleted >= 2 -> 2
            else -> 1
        }
}

data class FriendPeer(
    val name: String,
    val dailyReels: Int,
    val focusMinutesToday: Int,
    val level: Int
)

data class LevelTemplate(
    val templateLevel: Int,
    val title: String,
    val focusGoalText: String,
    val outdoorGoalText: String,
    val baseFpReward: Int
)

object ProgressionCatalog {
    val allPets: List<PetSpec> = listOf(
        PetSpec("axolotl", "Axolotl #AX-01", Biome.WATER, "pet_water_axolotl", 0),
        PetSpec("koi", "Sunburst Koi", Biome.WATER, "pet_water_koi", 180),
        PetSpec("jelly", "Moon Jelly", Biome.WATER, "pet_water_jelly", 360),
        PetSpec("wyrmling", "Night Wyrmling", Biome.AIR, "pet_air_wyrmling", 0),
        PetSpec("owl", "Gale Barn-Owl", Biome.AIR, "pet_air_owl", 180),
        PetSpec("moth", "Cloud Silk-Moth", Biome.AIR, "pet_air_moth", 360),
        PetSpec("tortoise", "Moss Tortoise", Biome.LAND, "pet_land_tortoise", 0),
        PetSpec("panda", "Dusk Red Panda", Biome.LAND, "pet_land_panda", 180),
        PetSpec("fennec", "Dune Fennec", Biome.LAND, "pet_land_fennec", 360)
    )

    val levels20: List<LevelTemplate> = listOf(
        LevelTemplate(1, "First Save", "Complete 2 focus sessions & stay under daily Reels cap", "10m sunlight / balcony break away from screens", 80),
        LevelTemplate(2, "Steady Ink", "Complete 5 focus blocks & finish 3 tasks", "15m phone-free outdoor walk", 90),
        LevelTemplate(3, "Scroll Brake", "Stay under daily Reels cap for 3 days", "10m outdoor stretch + hydrate with water", 100),
        LevelTemplate(4, "Deep Current", "Finish two 50m focus blocks in a day", "20m golden-hour outdoor check-in", 110),
        LevelTemplate(5, "First Grove", "Maintain a 5-day active streak", "25m park, coastal, or tree-lined walk", 125),
        LevelTemplate(6, "Morning Bell", "Complete a focus block before 10:00 AM twice", "15m fresh morning air before social apps", 115),
        LevelTemplate(7, "Clean Slate", "Complete 10 to-do tasks total", "Walk or cycle for a local errand", 120),
        LevelTemplate(8, "Zero Doom", "Keep daily Reels under 15 for 4 days", "45m screen-free evening wind-down", 130),
        LevelTemplate(9, "Iron Ribbon", "Complete 3 focus blocks in one day", "30m outdoor walk, jog, or cycle", 140),
        LevelTemplate(10, "Sanctuary Keeper", "Reach 25 total focus sessions", "Tech-free meal away from screens", 150),
        LevelTemplate(11, "Quiet Mind", "Complete a 50m block with zero breaches", "15m sky/cloud break outdoors", 145),
        LevelTemplate(12, "Friend Pace", "Stay under Reels cap & compare with friends", "Walk & talk with a friend or family member", 155),
        LevelTemplate(13, "Flow State", "Log 4+ hours of focus across 3 days", "40m outdoor exploration on a new route", 160),
        LevelTemplate(14, "Task Surgeon", "Complete 25 total tasks cleanly", "Read 10 pages of a physical book outdoors", 165),
        LevelTemplate(15, "Grand Botanist", "Grow 4 forest trees or bond 2 pets", "60m weekend outdoor walk or ride", 180),
        LevelTemplate(16, "Unbreakable", "10-day low-Reels streak", "20m morning daylight walk after waking", 175),
        LevelTemplate(17, "Marathon Ink", "Complete six 50m focus blocks in a week", "Step outside & log a quick nature note", 185),
        LevelTemplate(18, "Minimalist Monk", "Under 10 Reels/day for 5 days + 2 focus blocks/day", "2+ hours offline outdoor reset", 195),
        LevelTemplate(19, "Echoes of Focus", "Reach 75 total focus sessions", "45m sunset walk or ride without earbuds", 200),
        LevelTemplate(20, "Save Room Master", "Complete Lv. 20 milestones & 14-day rhythm", "Outdoor outing & unlock Endless Lv. 21+ Loop", 250)
    )

    fun templateForLevel(level: Int): LevelTemplate {
        val safeLevel = level.coerceAtLeast(1)
        val idx = (safeLevel - 1) % 20
        return levels20[idx]
    }

    fun prestigeCycle(level: Int): Int = ((level.coerceAtLeast(1)) - 1) / 20

    fun prestigeBadge(level: Int): String {
        val cycle = prestigeCycle(level)
        return if (cycle <= 0) "Lv.$level" else "Lv.$level ★$cycle"
    }
}

data class PlushieState(
    val operatorName: String = "Narendaran",
    val doorUnlocked: Boolean = false,
    val focusPoints: Int = 120,
    val herbPoints: Int = 120,
    val sanctuaryLevel: Int = 1,
    val completedFocusSessions: Int = 0,
    val completedTasksCount: Int = 0,
    val focusStreakDays: Int = 1,
    val levelFocusDone: Boolean = false,
    val levelOutdoorDone: Boolean = false,
    val sanctuaryMode: SanctuaryMode = SanctuaryMode.PET_ROOM,
    val activeBiome: Biome = Biome.WATER,
    val activePetId: String = "axolotl",
    val unlockedPetIds: Set<String> = setOf("axolotl", "wyrmling", "tortoise"),
    val petCustomNames: Map<String, String> = emptyMap(),
    val forestPlots: List<ForestPlot> = listOf(
        ForestPlot("plot-1", TreeSpecies.BIRCH, sessionsCompleted = 1)
    ),
    val dailyReelsWatched: Int = 4,
    val dailyReelsCap: Int = 15,
    val breachAlertActive: Boolean = false,
    val breachActive: Boolean = false,
    val isTimerRunning: Boolean = false,
    val timerModeBreak: Boolean = false,
    val remainingSeconds: Int = 1500,
    val targetEndTimeMs: Long = 0L,
    val sessionDistractionHits: Int = 0,
    val axolotlHunger: Int = 85,
    val axolotlAffection: Int = 80,
    val careAlertsEnabled: Boolean = false,
    val blockedPackages: List<String> = listOf("com.instagram.android"),
    val overlayEnabled: Boolean = false,
    val leonOverlayEnabled: Boolean = false,
    val crtScanlinesEnabled: Boolean = true,
    val saveRoomBackdropMode: Boolean = false,
    val selectedForestSpecies: TreeSpecies = TreeSpecies.BIRCH,
    val voiceTtsEnabled: Boolean = false,
    val posterFeedUrl: String = "",
    val posterAdminId: String = "narendaransg",
    val posterSigningKey: String = "",
    val tasks: List<TodoItem> = listOf(
        TodoItem("t1", "Complete 25m Save Room focus block", false),
        TodoItem("t2", "10-min outdoor sunlight / balcony break", false),
        TodoItem("t3", "Keep daily Reels under cap", false)
    ),
    val history: List<CompletedEventRecord> = emptyList(),
    val friends: List<FriendPeer> = listOf(
        FriendPeer("Riya", dailyReels = 6, focusMinutesToday = 75, level = 4),
        FriendPeer("Karthik", dailyReels = 11, focusMinutesToday = 50, level = 3),
        FriendPeer("Meera", dailyReels = 3, focusMinutesToday = 100, level = 6)
    )
) {
    val templateLevel: Int get() = ((sanctuaryLevel.coerceAtLeast(1)) - 1) % 20 + 1
    val prestigeCycle: Int get() = ProgressionCatalog.prestigeCycle(sanctuaryLevel)
    val canNamePets: Boolean get() = sanctuaryLevel >= 2 || focusPoints >= 150
    val maxPetSlots: Int
        get() = when {
            sanctuaryLevel >= 15 || focusPoints >= 1200 -> 5
            sanctuaryLevel >= 10 || focusPoints >= 700 -> 4
            sanctuaryLevel >= 5 || focusPoints >= 300 -> 3
            else -> 2
        }
    val carePoints: Int get() = focusPoints
    val streakDays: Int get() = focusStreakDays
    val focusSeconds: Int get() = remainingSeconds
    val dailyGoalMinutes: Int get() = 60
    val focusMinutesToday: Int get() = completedFocusSessions * 25

    fun petDisplayName(pet: PetSpec): String =
        petCustomNames[pet.id]?.takeIf { it.isNotBlank() } ?: pet.name

    fun petGrowthStage(pet: PetSpec): Int {
        val customLevel = ((completedFocusSessions + (focusPoints / 120)) / 2) + 1
        return when {
            customLevel >= 5 || sanctuaryLevel >= 8 -> 3
            customLevel >= 2 || sanctuaryLevel >= 3 -> 2
            else -> 1
        }
    }
}

object PlushieStorage {
    private const val PREFS_NAME = "save_room_plushie_v2"
    private const val KEY_JSON = "state_json"

    fun load(context: Context): PlushieState {
        val raw = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_JSON, null) ?: return PlushieState()
        return runCatching {
            val obj = JSONObject(raw)
            val unlockedArr = obj.optJSONArray("unlockedPetIds")
            val unlocked = mutableSetOf<String>()
            if (unlockedArr != null) {
                for (i in 0 until unlockedArr.length()) unlocked.add(unlockedArr.optString(i))
            }
            if (unlocked.isEmpty()) unlocked.addAll(listOf("axolotl", "wyrmling", "tortoise"))

            val namesObj = obj.optJSONObject("petCustomNames") ?: JSONObject()
            val names = mutableMapOf<String, String>()
            namesObj.keys().forEach { k -> names[k] = namesObj.optString(k) }

            val plotsArr = obj.optJSONArray("forestPlots") ?: JSONArray()
            val plots = mutableListOf<ForestPlot>()
            for (i in 0 until plotsArr.length()) {
                val p = plotsArr.optJSONObject(i) ?: continue
                val spId = p.optString("species", "birch")
                val sp = TreeSpecies.entries.firstOrNull { it.id == spId } ?: TreeSpecies.BIRCH
                plots.add(
                    ForestPlot(
                        id = p.optString("id", "plot-$i"),
                        species = sp,
                        sessionsCompleted = p.optInt("sessions", 1).coerceAtLeast(1)
                    )
                )
            }
            if (plots.isEmpty()) plots.add(ForestPlot("plot-1", TreeSpecies.BIRCH, 1))

            val tasksArr = obj.optJSONArray("tasks") ?: JSONArray()
            val tasks = mutableListOf<TodoItem>()
            for (i in 0 until tasksArr.length()) {
                val t = tasksArr.optJSONObject(i) ?: continue
                tasks.add(
                    TodoItem(
                        id = t.optString("id", "task-$i"),
                        title = t.optString("title", "Focus Task"),
                        done = t.optBoolean("done", false)
                    )
                )
            }

            val histArr = obj.optJSONArray("history") ?: JSONArray()
            val hist = mutableListOf<CompletedEventRecord>()
            for (i in 0 until histArr.length()) {
                val h = histArr.optJSONObject(i) ?: continue
                hist.add(
                    CompletedEventRecord(
                        id = h.optString("id", "h-$i"),
                        label = h.optString("label", "Completed Event"),
                        fpEarned = h.optInt("fp", 0),
                        timestampLabel = h.optString("time", "Today")
                    )
                )
            }

            val pkgsArr = obj.optJSONArray("blockedPackages")
            val pkgs = mutableListOf<String>()
            if (pkgsArr != null) {
                for (i in 0 until pkgsArr.length()) pkgs.add(pkgsArr.optString(i))
            }
            if (pkgs.isEmpty()) pkgs.add("com.instagram.android")

            val biomeStr = obj.optString("activeBiome", Biome.WATER.name)
            val activeBiome = Biome.entries.firstOrNull { it.name == biomeStr } ?: Biome.WATER
            val modeStr = obj.optString("sanctuaryMode", SanctuaryMode.PET_ROOM.name)
            val mode = SanctuaryMode.entries.firstOrNull { it.name == modeStr } ?: SanctuaryMode.PET_ROOM

            PlushieState(
                operatorName = obj.optString("operatorName", "Narendaran"),
                doorUnlocked = obj.optBoolean("doorUnlocked", false),
                focusPoints = obj.optInt("focusPoints", 120),
                herbPoints = obj.optInt("herbPoints", obj.optInt("focusPoints", 120)),
                sanctuaryLevel = obj.optInt("sanctuaryLevel", 1).coerceAtLeast(1),
                completedFocusSessions = obj.optInt("completedFocusSessions", 0),
                completedTasksCount = obj.optInt("completedTasksCount", 0),
                focusStreakDays = obj.optInt("focusStreakDays", 1).coerceAtLeast(1),
                levelFocusDone = obj.optBoolean("levelFocusDone", false),
                levelOutdoorDone = obj.optBoolean("levelOutdoorDone", false),
                sanctuaryMode = mode,
                activeBiome = activeBiome,
                activePetId = obj.optString("activePetId", "axolotl"),
                unlockedPetIds = unlocked,
                petCustomNames = names,
                forestPlots = plots,
                dailyReelsWatched = obj.optInt("dailyReelsWatched", 4),
                dailyReelsCap = obj.optInt("dailyReelsCap", 15).coerceAtLeast(1),
                breachAlertActive = obj.optBoolean("breachAlertActive", false),
                breachActive = obj.optBoolean("breachActive", false),
                isTimerRunning = obj.optBoolean("isTimerRunning", false),
                timerModeBreak = obj.optBoolean("timerModeBreak", false),
                remainingSeconds = obj.optInt("remainingSeconds", 1500),
                targetEndTimeMs = obj.optLong("targetEndTimeMs", 0L),
                sessionDistractionHits = obj.optInt("sessionDistractionHits", 0),
                axolotlHunger = obj.optInt("axolotlHunger", 85),
                axolotlAffection = obj.optInt("axolotlAffection", 80),
                careAlertsEnabled = obj.optBoolean("careAlertsEnabled", false),
                blockedPackages = pkgs,
                overlayEnabled = obj.optBoolean("overlayEnabled", false),
                leonOverlayEnabled = obj.optBoolean("leonOverlayEnabled", obj.optBoolean("overlayEnabled", false)),
                crtScanlinesEnabled = obj.optBoolean("crtScanlinesEnabled", true),
                voiceTtsEnabled = obj.optBoolean("voiceTtsEnabled", false),
                posterFeedUrl = obj.optString("posterFeedUrl", ""),
                posterAdminId = obj.optString("posterAdminId", "narendaransg"),
                posterSigningKey = obj.optString("posterSigningKey", ""),
                tasks = tasks,
                history = hist
            )
        }.getOrElse { PlushieState() }
    }

    fun save(context: Context, state: PlushieState) {
        val obj = JSONObject().apply {
            put("operatorName", state.operatorName)
            put("doorUnlocked", state.doorUnlocked)
            put("focusPoints", state.focusPoints)
            put("herbPoints", state.herbPoints)
            put("sanctuaryLevel", state.sanctuaryLevel)
            put("completedFocusSessions", state.completedFocusSessions)
            put("completedTasksCount", state.completedTasksCount)
            put("focusStreakDays", state.focusStreakDays)
            put("levelFocusDone", state.levelFocusDone)
            put("levelOutdoorDone", state.levelOutdoorDone)
            put("sanctuaryMode", state.sanctuaryMode.name)
            put("activeBiome", state.activeBiome.name)
            put("activePetId", state.activePetId)
            put("unlockedPetIds", JSONArray(state.unlockedPetIds.toList()))
            put("petCustomNames", JSONObject(state.petCustomNames))
            put("forestPlots", JSONArray().apply {
                state.forestPlots.forEach { p ->
                    put(JSONObject().apply {
                        put("id", p.id)
                        put("species", p.species.id)
                        put("sessions", p.sessionsCompleted)
                    })
                }
            })
            put("dailyReelsWatched", state.dailyReelsWatched)
            put("dailyReelsCap", state.dailyReelsCap)
            put("breachAlertActive", state.breachAlertActive)
            put("breachActive", state.breachActive)
            put("isTimerRunning", state.isTimerRunning)
            put("timerModeBreak", state.timerModeBreak)
            put("remainingSeconds", state.remainingSeconds)
            put("targetEndTimeMs", state.targetEndTimeMs)
            put("sessionDistractionHits", state.sessionDistractionHits)
            put("axolotlHunger", state.axolotlHunger)
            put("axolotlAffection", state.axolotlAffection)
            put("careAlertsEnabled", state.careAlertsEnabled)
            put("blockedPackages", JSONArray(state.blockedPackages))
            put("overlayEnabled", state.overlayEnabled)
            put("leonOverlayEnabled", state.leonOverlayEnabled)
            put("crtScanlinesEnabled", state.crtScanlinesEnabled)
            put("voiceTtsEnabled", state.voiceTtsEnabled)
            put("posterFeedUrl", state.posterFeedUrl)
            put("posterAdminId", state.posterAdminId)
            put("posterSigningKey", state.posterSigningKey)
            put("tasks", JSONArray().apply {
                state.tasks.forEach { t ->
                    put(JSONObject().apply {
                        put("id", t.id)
                        put("title", t.title)
                        put("done", t.done)
                    })
                }
            })
            put("history", JSONArray().apply {
                state.history.take(50).forEach { h ->
                    put(JSONObject().apply {
                        put("id", h.id)
                        put("label", h.label)
                        put("fp", h.fpEarned)
                        put("time", h.timestampLabel)
                    })
                }
            })
        }
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_JSON, obj.toString())
            .apply()
    }
}

class PlushiePrefs(private val context: Context) {
    fun loadInitial(): PlushieState = PlushieStorage.load(context)
    fun save(state: PlushieState) = PlushieStorage.save(context, state)

    companion object {
        fun loadInitial(context: Context): PlushieState = PlushieStorage.load(context)
        fun save(context: Context, state: PlushieState) = PlushieStorage.save(context, state)
    }
}

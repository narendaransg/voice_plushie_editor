package com.raccoon.plushie.poster

import android.content.Context
import android.content.Intent
import androidx.compose.runtime.Immutable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

@Immutable
data class SaveRoomPoster(
    val posterId: String,
    val title: String,
    val message: String,
    val badgeTag: String = "CREATOR DISPATCH · VERIFIED",
    val adminId: String = "",
    val minVersionCode: Int = 1,
    val expiresAtEpochMs: Long = Long.MAX_VALUE
)

@Immutable
data class FeedbackEntry(
    val id: String,
    val category: String,
    val note: String,
    val createdAtMs: Long
)

object RemotePosterRepository {
    private const val PREFS_NAME = "raccoon_poster_prefs"
    private const val KEY_ENDPOINT_URL = "remote_poster_https_url"
    private const val KEY_ADMIN_ID = "admin_creator_id"
    private const val KEY_ADMIN_SIGNING_KEY = "admin_signing_key"
    private const val KEY_DISMISSED_IDS = "dismissed_poster_ids"
    private const val KEY_CACHED_JSON = "cached_poster_json"
    private const val KEY_FEEDBACK_JSON = "user_feedback_json"
    private const val KEY_TUTORIAL_DONE = "first_time_tutorial_done"

    // Default admin identity for Narendaran S G; set a signing key in Feed URL settings to enforce SHA-256 verification
    const val DEFAULT_ADMIN_ID = "narendaransg"

    private val defaultPoster = SaveRoomPoster(
        posterId = "welcome-v070",
        title = "SAVE ROOM TRANSMISSION #01",
        message = "Admin-verified Save Room dispatch channel ready. Configure your HTTPS feed & admin signing key to publish posters safely.",
        badgeTag = "SAVE ROOM ARCHIVE",
        adminId = DEFAULT_ADMIN_ID
    )

    fun isTutorialCompleted(context: Context): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getBoolean(KEY_TUTORIAL_DONE, false)
    }

    fun setTutorialCompleted(context: Context, done: Boolean) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_TUTORIAL_DONE, done)
            .apply()
    }

    fun getConfiguredUrl(context: Context): String {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_ENDPOINT_URL, "")
            .orEmpty()
    }

    fun getAdminId(context: Context): String {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_ADMIN_ID, DEFAULT_ADMIN_ID)
            .orEmpty()
            .ifBlank { DEFAULT_ADMIN_ID }
    }

    fun getSigningKey(context: Context): String {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_ADMIN_SIGNING_KEY, "")
            .orEmpty()
    }

    fun saveAdminFeedConfig(context: Context, rawUrl: String, adminId: String, signingKey: String): Boolean {
        val trimmedUrl = rawUrl.trim()
        if (trimmedUrl.isNotEmpty() && !trimmedUrl.startsWith("https://", ignoreCase = true)) {
            return false
        }
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_ENDPOINT_URL, trimmedUrl)
            .putString(KEY_ADMIN_ID, adminId.trim().ifBlank { DEFAULT_ADMIN_ID })
            .putString(KEY_ADMIN_SIGNING_KEY, signingKey.trim())
            .apply()
        return true
    }

    fun computePosterDigest(posterId: String, title: String, message: String, signingKey: String): String {
        val input = "$posterId|$title|$message|$signingKey"
        val bytes = MessageDigest.getInstance("SHA-256").digest(input.toByteArray(Charsets.UTF_8))
        return bytes.joinToString("") { "%02x".format(it) }
    }

    fun dismissPoster(context: Context, posterId: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val existing = prefs.getStringSet(KEY_DISMISSED_IDS, emptySet()).orEmpty().toMutableSet()
        existing.add(posterId)
        prefs.edit().putStringSet(KEY_DISMISSED_IDS, existing).apply()
    }

    fun resetDismissed(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_DISMISSED_IDS)
            .apply()
    }

    suspend fun fetchActivePoster(context: Context, appVersionCode: Int): SaveRoomPoster? = withContext(Dispatchers.IO) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val dismissed = prefs.getStringSet(KEY_DISMISSED_IDS, emptySet()).orEmpty()
        val urlStr = prefs.getString(KEY_ENDPOINT_URL, "").orEmpty().trim()
        val expectedAdmin = getAdminId(context)
        val signingKey = getSigningKey(context)
        val now = System.currentTimeMillis()

        var candidates: List<SaveRoomPoster> = emptyList()
        if (urlStr.startsWith("https://", ignoreCase = true)) {
            try {
                val conn = (URL(urlStr).openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    connectTimeout = 4500
                    readTimeout = 4500
                    setRequestProperty("Accept", "application/json")
                }
                if (conn.responseCode in 200..299) {
                    val body = conn.inputStream.bufferedReader().use { it.readText() }
                    if (body.length <= 32_768) {
                        val parsed = parseVerifiedFeedJson(body, expectedAdmin, signingKey)
                        if (parsed.isNotEmpty()) {
                            candidates = parsed
                            prefs.edit().putString(KEY_CACHED_JSON, body).apply()
                        }
                    }
                }
                conn.disconnect()
            } catch (_: Exception) {
            }
        }

        if (candidates.isEmpty()) {
            val cached = prefs.getString(KEY_CACHED_JSON, null)
            if (!cached.isNullOrBlank()) {
                candidates = parseVerifiedFeedJson(cached, expectedAdmin, signingKey)
            }
        }

        if (candidates.isEmpty()) {
            candidates = listOf(defaultPoster)
        }

        candidates.firstOrNull { p ->
            p.posterId !in dismissed &&
                appVersionCode >= p.minVersionCode &&
                now <= p.expiresAtEpochMs
        }
    }

    fun loadFeedback(context: Context): List<FeedbackEntry> {
        val raw = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_FEEDBACK_JSON, null) ?: return emptyList()
        return try {
            val arr = JSONArray(raw)
            (0 until arr.length()).map { i ->
                val o = arr.getJSONObject(i)
                FeedbackEntry(
                    id = o.optString("id", "fb-$i"),
                    category = o.optString("category", "Suggestion"),
                    note = o.optString("note", ""),
                    createdAtMs = o.optLong("createdAtMs", 0L)
                )
            }.filter { it.note.isNotBlank() }
        } catch (_: Exception) {
            emptyList()
        }
    }

    fun addFeedback(context: Context, category: String, note: String): List<FeedbackEntry> {
        val trimmed = note.trim()
        if (trimmed.isEmpty()) return loadFeedback(context)
        val updated = listOf(
            FeedbackEntry(
                id = "fb-${System.currentTimeMillis()}",
                category = category.trim().ifBlank { "Suggestion" },
                note = trimmed.take(400),
                createdAtMs = System.currentTimeMillis()
            )
        ) + loadFeedback(context)
        val arr = JSONArray()
        updated.take(25).forEach { e ->
            arr.put(
                JSONObject().apply {
                    put("id", e.id)
                    put("category", e.category)
                    put("note", e.note)
                    put("createdAtMs", e.createdAtMs)
                }
            )
        }
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_FEEDBACK_JSON, arr.toString())
            .apply()
        return updated
    }

    fun shareFeedbackIntent(entries: List<FeedbackEntry>): Intent {
        val body = if (entries.isEmpty()) {
            "Save Room Plushie Feedback:\n"
        } else {
            entries.take(5).joinToString("\n\n") { "[${it.category}] ${it.note}" }
        }
        return Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_SUBJECT, "Save Room Plushie — Feedback & Suggestions")
            putExtra(Intent.EXTRA_TEXT, body)
        }
    }

    private fun parseVerifiedFeedJson(raw: String, expectedAdmin: String, signingKey: String): List<SaveRoomPoster> {
        return try {
            val root = JSONObject(raw)
            if (root.has("posters") && root.opt("posters") is JSONArray) {
                val arr = root.getJSONArray("posters")
                (0 until arr.length()).mapNotNull { i ->
                    parseAndVerifySingle(arr.optJSONObject(i), expectedAdmin, signingKey)
                }
            } else {
                listOfNotNull(parseAndVerifySingle(root, expectedAdmin, signingKey))
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun parseAndVerifySingle(
        obj: JSONObject?,
        expectedAdmin: String,
        signingKey: String
    ): SaveRoomPoster? {
        if (obj == null) return null
        val id = obj.optString("poster_id").trim()
        val title = obj.optString("title").trim()
        val msg = obj.optString("message").trim()
        val adminId = obj.optString("admin_id").trim()
        val sha256Sig = obj.optString("sha256").trim().lowercase()

        if (id.isEmpty() || title.isEmpty() || msg.isEmpty()) return null
        if (adminId.isNotEmpty() && adminId != expectedAdmin) return null

        // When a signing key is configured on the device, require a matching SHA-256 signature
        if (signingKey.isNotEmpty()) {
            val expectedSig = computePosterDigest(id, title, msg, signingKey)
            if (sha256Sig != expectedSig) return null
        }

        return SaveRoomPoster(
            posterId = id.take(64),
            title = title.take(120),
            message = msg.take(600),
            badgeTag = obj.optString("badge_tag", "ADMIN VERIFIED").take(64),
            adminId = adminId.ifBlank { expectedAdmin },
            minVersionCode = obj.optInt("min_version", 1),
            expiresAtEpochMs = obj.optLong("expires_at", Long.MAX_VALUE)
        )
    }
}

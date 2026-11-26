package com.raccoon.plushie.care

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import com.raccoon.plushie.MainActivity
import com.raccoon.plushie.data.PlushiePrefs

class AxolotlCareService : Service() {

    companion object {
        const val CHANNEL_ID = "raccoon_care_live_channel"
        const val ACTION_START_CARE = "com.raccoon.plushie.START_CARE_TRACKER"
        const val ACTION_STOP_CARE = "com.raccoon.plushie.STOP_CARE_TRACKER"
        const val ACTION_REFRESH_NOW = "com.raccoon.plushie.REFRESH_CARE_NOW"
        const val ACTION_CARE_UPDATED = "com.raccoon.plushie.CARE_STATE_UPDATED"
        const val NOTIF_ID = 7710
    }

    private val handler = Handler(Looper.getMainLooper())
    private var active = false

    private val careTickRunnable = object : Runnable {
        override fun run() {
            if (!active) return
            val prefs = PlushiePrefs(this@AxolotlCareService)
            val cur = prefs.loadInitial()
            if (!cur.careAlertsEnabled) {
                stopSelf()
                return
            }

            val nextHunger = (cur.axolotlHunger - 2).coerceAtLeast(0)
            val nextBond = (cur.axolotlAffection - 1).coerceAtLeast(0)
            val updated = cur.copy(
                axolotlHunger = nextHunger,
                axolotlAffection = nextBond
            )
            prefs.save(updated)
            postLiveNotification(nextHunger, nextBond, updated.streakDays)
            sendBroadcast(Intent(ACTION_CARE_UPDATED).setPackage(packageName))
            handler.postDelayed(this, 45_000L)
        }
    }

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP_CARE -> {
                active = false
                handler.removeCallbacks(careTickRunnable)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                    stopForeground(STOP_FOREGROUND_REMOVE)
                } else {
                    @Suppress("DEPRECATION")
                    stopForeground(true)
                }
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_REFRESH_NOW -> {
                val cur = PlushiePrefs(this).loadInitial()
                if (cur.careAlertsEnabled) {
                    active = true
                    startForeground(NOTIF_ID, buildLiveNotification(cur.axolotlHunger, cur.axolotlAffection, cur.streakDays))
                }
                return START_STICKY
            }
            else -> {
                val cur = PlushiePrefs(this).loadInitial()
                active = true
                startForeground(NOTIF_ID, buildLiveNotification(cur.axolotlHunger, cur.axolotlAffection, cur.streakDays))
                handler.removeCallbacks(careTickRunnable)
                handler.postDelayed(careTickRunnable, 45_000L)
                return START_STICKY
            }
        }
    }

    private fun postLiveNotification(hunger: Int, bond: Int, streak: Int) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(NOTIF_ID, buildLiveNotification(hunger, bond, streak))
    }

    private fun buildLiveNotification(hunger: Int, bond: Int, streak: Int): Notification {
        val openIntent = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        val pi = PendingIntent.getActivity(
            this,
            7710,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val statusMood = when {
            hunger <= 30 -> "Hungry! Needs Herb snack"
            bond <= 35 -> "Lonely! Tap to pet"
            else -> "Happy & swimming"
        }

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.star_on)
            .setContentTitle("Axolotl #AX-01 · $statusMood")
            .setContentText("Fullness: $hunger% · Bond: $bond% · Streak: ${streak}d")
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setContentIntent(pi)
            .build()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val ch = NotificationChannel(
                CHANNEL_ID,
                "Live Axolotl Care Tracker",
                NotificationManager.IMPORTANCE_LOW
            )
            nm.createNotificationChannel(ch)
        }
    }

    override fun onDestroy() {
        active = false
        handler.removeCallbacks(careTickRunnable)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}

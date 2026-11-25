package com.raccoon.plushie.service

import android.app.ActivityManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import com.raccoon.plushie.MainActivity
import com.raccoon.plushie.R

class ContainmentService : Service() {

    companion object {
        const val CHANNEL_ID = "raccoon_containment_channel"
        const val ACTION_START_LOCK = "com.raccoon.plushie.START_LOCK"
        const val ACTION_STOP_LOCK = "com.raccoon.plushie.STOP_LOCK"
        const val TARGET_INSTAGRAM = "com.instagram.android"

        fun hasUsageStatsPermission(context: Context): Boolean {
            val usm = context.getSystemService(Context.USAGE_STATS_SERVICE) as? UsageStatsManager ?: return false
            val now = System.currentTimeMillis()
            val events = usm.queryEvents(now - 60_000L, now)
            val event = UsageEvents.Event()
            while (events.hasNextEvent()) {
                events.getNextEvent(event)
                if (event.packageName != null) return true
            }
            val stats = usm.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, now - 86_400_000L, now)
            return !stats.isNullOrEmpty()
        }
    }

    private val handler = Handler(Looper.getMainLooper())
    private var lockActive = false
    private var windowManager: WindowManager? = null
    private var shieldView: LinearLayout? = null
    private var lastAlertShownMs = 0L

    private val monitorRunnable = object : Runnable {
        override fun run() {
            if (lockActive) {
                val fgPkg = queryForegroundPackage()
                val now = System.currentTimeMillis()
                if (fgPkg == TARGET_INSTAGRAM && now - lastAlertShownMs > 2500L) {
                    lastAlertShownMs = now
                    showShieldOverlay()
                }
            }
            handler.postDelayed(this, 1200L)
        }
    }

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP_LOCK -> {
                lockActive = false
                removeShieldOverlay()
                handler.removeCallbacks(monitorRunnable)
                stopForeground(true)
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                lockActive = true
                startForeground(1042, buildNotification())
                handler.removeCallbacks(monitorRunnable)
                handler.post(monitorRunnable)
                return START_STICKY
            }
        }
    }

    private fun queryForegroundPackage(): String? {
        val usm = getSystemService(Context.USAGE_STATS_SERVICE) as? UsageStatsManager
        if (usm != null) {
            val now = System.currentTimeMillis()
            val events = usm.queryEvents(now - 5_000L, now)
            val ev = UsageEvents.Event()
            var latestPkg: String? = null
            while (events.hasNextEvent()) {
                events.getNextEvent(ev)
                if (ev.eventType == UsageEvents.Event.MOVE_TO_FOREGROUND ||
                    ev.eventType == UsageEvents.Event.ACTIVITY_RESUMED
                ) {
                    latestPkg = ev.packageName
                }
            }
            if (latestPkg != null) return latestPkg
        }

        val am = getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
        return am?.runningAppProcesses?.firstOrNull {
            it.importance == ActivityManager.RunningAppProcessInfo.IMPORTANCE_FOREGROUND
        }?.pkgList?.firstOrNull()
    }

    private fun showShieldOverlay() {
        if (shieldView != null) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) return

        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        windowManager = wm

        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 64, 48, 64)
            setBackgroundColor(0xF0101512.toInt())
        }

        val title = TextView(this).apply {
            text = "BIOHAZARD CONTAINMENT: SAVE ROOM ACTIVE"
            setTextColor(0xFF6EE7B7.toInt())
            textSize = 18f
        }

        val body = TextView(this).apply {
            text = "Instagram / Reels signal intercepted.\nYour plushie & shiny axolotl are holding the Safe Room."
            setTextColor(0xFFE5E7EB.toInt())
            textSize = 14f
        }

        val returnBtn = Button(this).apply {
            text = "Back to Save Room"
            setOnClickListener {
                removeShieldOverlay()
                val launchIntent = Intent(this@ContainmentService, MainActivity::class.java).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                }
                startActivity(launchIntent)
            }
        }

        box.addView(title)
        box.addView(body)
        box.addView(returnBtn)

        @Suppress("DEPRECATION")
        val overlayType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            WindowManager.LayoutParams.TYPE_PHONE
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            overlayType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.CENTER
        }

        shieldView = box
        wm.addView(box, params)
    }

    private fun removeShieldOverlay() {
        val view = shieldView ?: return
        try {
            windowManager?.removeView(view)
        } catch (_: Exception) {
        } finally {
            shieldView = null
        }
    }

    private fun buildNotification(): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setContentTitle("Save Room Bio-Shield Active")
            .setContentText("Guarding study session against Instagram doomscrolling")
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .setContentIntent(openIntent)
            .setOngoing(true)
            .build()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val ch = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.shield_channel_name),
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = getString(R.string.shield_channel_desc)
            }
            nm.createNotificationChannel(ch)
        }
    }

    override fun onDestroy() {
        lockActive = false
        removeShieldOverlay()
        handler.removeCallbacks(monitorRunnable)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}

package com.raccoon.plushie.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
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
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.app.NotificationCompat
import com.raccoon.plushie.MainActivity
import com.raccoon.plushie.data.PlushiePrefs
import com.raccoon.plushie.overlay.LeonOverlayService

class ContainmentService : Service() {

    companion object {
        const val CHANNEL_ID = "raccoon_containment_channel"
        const val NOTIF_ID = 4042
        const val ACTION_START_LOCK = "com.raccoon.plushie.START_CONTAINMENT_LOCK"
        const val ACTION_STOP_LOCK = "com.raccoon.plushie.STOP_CONTAINMENT_LOCK"
        const val EXTRA_BLOCKED_PKGS = "extra_blocked_packages"

        fun hasUsageStatsPermission(context: Context): Boolean {
            val usm = context.getSystemService(Context.USAGE_STATS_SERVICE) as? UsageStatsManager ?: return false
            val now = System.currentTimeMillis()
            val events = usm.queryEvents(now - 60_000L, now)
            return (events != null && events.hasNextEvent()) ||
                !usm.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, now - 86_400_000L, now).isNullOrEmpty()
        }
    }

    private val handler = Handler(Looper.getMainLooper())
    private var windowManager: WindowManager? = null
    private var shieldView: View? = null
    private var activeBlockedPackages: Set<String> = setOf("com.instagram.android")
    private var isLockActive = false
    private var warningSecondsLeft = 10
    private var interceptedPkg: String? = null

    private val pollRunnable = object : Runnable {
        override fun run() {
            if (!isLockActive) return
            val prefs = PlushiePrefs(this@ContainmentService)
            val cur = prefs.loadInitial()
            if (!cur.isTimerRunning || cur.timerModeBreak) {
                removeShieldOverlay()
                handler.postDelayed(this, 1200L)
                return
            }

            val fgPkg = detectForegroundPackage()
            val blockedNow = fgPkg != null &&
                fgPkg != packageName &&
                fgPkg in activeBlockedPackages

            if (blockedNow) {
                if (interceptedPkg != fgPkg) {
                    interceptedPkg = fgPkg
                    warningSecondsLeft = 10
                    prefs.save(cur.copy(sessionDistractionHits = cur.sessionDistractionHits + 1))
                    try {
                        startService(
                            Intent(this@ContainmentService, LeonOverlayService::class.java).apply {
                                action = LeonOverlayService.ACTION_TRIGGER_SHIELD_POSE
                            }
                        )
                    } catch (_: Exception) {
                    }
                }
                showOrUpdateShieldOverlay(fgPkg!!, warningSecondsLeft)
                if (warningSecondsLeft <= 0) {
                    exitBlockedAppToHome()
                    removeShieldOverlay()
                    interceptedPkg = null
                    warningSecondsLeft = 10
                } else {
                    warningSecondsLeft -= 1
                }
            } else {
                interceptedPkg = null
                warningSecondsLeft = 10
                removeShieldOverlay()
            }

            handler.postDelayed(this, 1000L)
        }
    }

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP_LOCK -> {
                isLockActive = false
                interceptedPkg = null
                warningSecondsLeft = 10
                handler.removeCallbacks(pollRunnable)
                removeShieldOverlay()
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                    stopForeground(STOP_FOREGROUND_REMOVE)
                } else {
                    @Suppress("DEPRECATION")
                    stopForeground(true)
                }
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                val list = intent?.getStringArrayListExtra(EXTRA_BLOCKED_PKGS)
                if (!list.isNullOrEmpty()) {
                    activeBlockedPackages = list.toSet()
                }
                isLockActive = true
                startForeground(NOTIF_ID, buildForegroundNotification())
                handler.removeCallbacks(pollRunnable)
                handler.post(pollRunnable)
                return START_STICKY
            }
        }
    }

    private fun detectForegroundPackage(): String? {
        if (!hasUsageStatsPermission(this)) return null
        val usm = getSystemService(Context.USAGE_STATS_SERVICE) as? UsageStatsManager ?: return null
        val end = System.currentTimeMillis()
        val begin = end - 10_000L
        val stats = usm.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, begin, end)
        if (stats.isNullOrEmpty()) return null
        return stats.maxByOrNull { it.lastTimeUsed }?.packageName
    }

    private fun exitBlockedAppToHome() {
        try {
            val homeIntent = Intent(Intent.ACTION_MAIN).apply {
                addCategory(Intent.CATEGORY_HOME)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(homeIntent)
        } catch (_: Exception) {
        }
    }

    private fun showOrUpdateShieldOverlay(pkg: String, secondsRemaining: Int) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) return
        val wm = getSystemService(Context.WINDOW_SERVICE) as? WindowManager ?: return
        windowManager = wm

        val existing = shieldView
        if (existing != null) {
            existing.findViewById<TextView>(android.R.id.text1)?.text = "CONTAINMENT WARNING · EXIT IN ${secondsRemaining}s"
            existing.findViewById<TextView>(android.R.id.text2)?.text = "Blocked during focus: $pkg"
            return
        }

        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 36, 36, 36)
            setBackgroundColor(0xF20B1310.toInt())
        }

        val titleTv = TextView(this).apply {
            id = android.R.id.text1
            text = "CONTAINMENT WARNING · EXIT IN ${secondsRemaining}s"
            setTextColor(0xFF34D399.toInt())
            textSize = 16f
        }

        val subTv = TextView(this).apply {
            id = android.R.id.text2
            text = "Blocked during focus: $pkg"
            setTextColor(0xFFF3F4F6.toInt())
            textSize = 13f
            setPadding(0, 8, 0, 16)
        }

        val returnBtn = Button(this).apply {
            text = "Return to Save Room Now"
            setOnClickListener {
                removeShieldOverlay()
                val openIntent = Intent(this@ContainmentService, MainActivity::class.java).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                }
                startActivity(openIntent)
            }
        }

        val exitNowBtn = Button(this).apply {
            text = "Exit App Now"
            setOnClickListener {
                removeShieldOverlay()
                exitBlockedAppToHome()
            }
        }

        box.addView(titleTv)
        box.addView(subTv)
        box.addView(returnBtn)
        box.addView(exitNowBtn)

        @Suppress("DEPRECATION")
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            WindowManager.LayoutParams.TYPE_PHONE
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.CENTER
            x = 24
            y = 0
        }

        try {
            wm.addView(box, params)
            shieldView = box
        } catch (_: Exception) {
            shieldView = null
        }
    }

    private fun removeShieldOverlay() {
        val v = shieldView ?: return
        try {
            windowManager?.removeView(v)
        } catch (_: Exception) {
        } finally {
            shieldView = null
        }
    }

    private fun buildForegroundNotification(): Notification {
        val openIntent = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        val pi = PendingIntent.getActivity(
            this,
            0,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .setContentTitle("Save Room Bio-Shield Armed")
            .setContentText("10s warning before exiting blocked apps during focus blocks")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setContentIntent(pi)
            .build()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val ch = NotificationChannel(
                CHANNEL_ID,
                "Biohazard Containment Shield",
                NotificationManager.IMPORTANCE_LOW
            )
            nm.createNotificationChannel(ch)
        }
    }

    override fun onDestroy() {
        isLockActive = false
        handler.removeCallbacks(pollRunnable)
        removeShieldOverlay()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}

package com.raccoon.plushie.overlay

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.raccoon.plushie.MainActivity
import com.raccoon.plushie.R
import com.raccoon.plushie.care.AxolotlCareService
import com.raccoon.plushie.data.PlushiePrefs
import com.raccoon.plushie.service.ContainmentService
import java.util.Locale
import kotlin.math.abs

class LeonOverlayService : Service() {

    companion object {
        const val CHANNEL_ID = "raccoon_leon_overlay_channel"
        const val ACTION_START_LEON = "com.raccoon.plushie.START_LEON_OVERLAY"
        const val ACTION_STOP_LEON = "com.raccoon.plushie.STOP_LEON_OVERLAY"
        const val ACTION_TRIGGER_SHIELD_POSE = "com.raccoon.plushie.LEON_SHIELD_POSE"
        const val ACTION_OVERLAY_STATE_CHANGED = "com.raccoon.plushie.OVERLAY_STATE_CHANGED"
    }

    private val idleDialogues = listOf(
        "Stay sharp. Save Room perimeter is clear.",
        "Ink ribbon primed. Ready when you are.",
        "Tap me anytime for quick Save Room controls."
    )
    private val lockDialogues = listOf(
        "Lock engaged. Eyes on your study drill.",
        "Holding the perimeter—zero distractions.",
        "Steady pace. Typewriter save is waiting."
    )
    private val careDialogues = listOf(
        "Specimen #AX-01 appreciated that herb care.",
        "Axolotl looks hungry—toss it a herb snack.",
        "Bond levels rising. Keep the tank thriving."
    )

    private var windowManager: WindowManager? = null
    private var floatingView: View? = null
    private var menuContainer: LinearLayout? = null
    private var speechTextView: TextView? = null
    private var statusTextView: TextView? = null
    private var toggleBtnView: Button? = null
    private var leonImageView: ImageView? = null

    private var menuExpanded = false
    private var dialogueIndex = 0
    private var frameIndex = 0
    private var shieldBoostUntilMs = 0L
    private var careBoostUntilMs = 0L

    private var currentSheetResId = 0
    private var cachedSheetBitmap: Bitmap? = null
    private val handler = Handler(Looper.getMainLooper())

    private val animAndStatusRunnable = object : Runnable {
        override fun run() {
            frameIndex = (frameIndex + 1) % 3
            updateLeonSpriteAndStatus()
            if (floatingView != null) {
                handler.postDelayed(this, 420L)
            }
        }
    }

    private val dialogueRunnable = object : Runnable {
        override fun run() {
            dialogueIndex += 1
            updateDialogueText()
            if (floatingView != null) {
                handler.postDelayed(this, 6000L)
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP_LEON -> {
                removeOverlay()
                handler.removeCallbacks(animAndStatusRunnable)
                handler.removeCallbacks(dialogueRunnable)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                    stopForeground(STOP_FOREGROUND_REMOVE)
                } else {
                    @Suppress("DEPRECATION")
                    stopForeground(true)
                }
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_TRIGGER_SHIELD_POSE -> {
                shieldBoostUntilMs = System.currentTimeMillis() + 5000L
                speechTextView?.text = "Blocked app intercepted! Back to Save Room."
                updateLeonSpriteAndStatus()
                return START_STICKY
            }
        }

        startForeground(1088, buildNotification())
        showLeonFloatingCharacter()
        handler.removeCallbacks(animAndStatusRunnable)
        handler.removeCallbacks(dialogueRunnable)
        handler.post(animAndStatusRunnable)
        handler.postDelayed(dialogueRunnable, 6000L)
        return START_STICKY
    }

    private fun resolveActionSheet(): Int {
        val now = System.currentTimeMillis()
        val st = PlushiePrefs(this).loadInitial()
        return when {
            now < shieldBoostUntilMs -> R.drawable.leon_action_shield
            now < careBoostUntilMs || st.axolotlHunger <= 35 -> R.drawable.leon_action_care
            st.isTimerRunning -> R.drawable.leon_action_lock
            else -> R.drawable.sheet_leon_cheer
        }
    }

    private fun updateDialogueText() {
        val now = System.currentTimeMillis()
        if (now < shieldBoostUntilMs) return
        val st = PlushiePrefs(this).loadInitial()
        val pool = when {
            now < careBoostUntilMs || st.axolotlHunger <= 35 -> careDialogues
            st.isTimerRunning -> lockDialogues
            else -> idleDialogues
        }
        speechTextView?.text = pool[dialogueIndex % pool.size]
    }

    private fun updateLeonSpriteAndStatus() {
        val st = PlushiePrefs(this).loadInitial()
        val now = System.currentTimeMillis()
        val remSec = if (st.isTimerRunning && st.targetEndTimeMs > 0L) {
            ((st.targetEndTimeMs - now) / 1000L).toInt().coerceAtLeast(0)
        } else {
            st.remainingSeconds
        }
        val clock = String.format(Locale.getDefault(), "%02d:%02d", remSec / 60, remSec % 60)
        statusTextView?.text = "${if (st.isTimerRunning) "LOCK" else "IDLE"} $clock · H:${st.axolotlHunger}% ♥${st.axolotlAffection}%"
        toggleBtnView?.text = if (st.isTimerRunning) "Pause" else "Start"

        val targetRes = resolveActionSheet()
        if (targetRes != currentSheetResId || cachedSheetBitmap == null) {
            currentSheetResId = targetRes
            cachedSheetBitmap = BitmapFactory.decodeResource(resources, targetRes)
        }
        val sheet = cachedSheetBitmap ?: return
        if (sheet.width >= 3 && sheet.height > 0) {
            val frameW = sheet.width / 3
            val safeX = (frameIndex % 3) * frameW
            val slice = Bitmap.createBitmap(sheet, safeX, 0, frameW, sheet.height)
            leonImageView?.setImageBitmap(slice)
        }
    }

    private fun showLeonFloatingCharacter() {
        if (floatingView != null) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) return

        val wm = getSystemService(Context.WINDOW_SERVICE) as? WindowManager ?: return
        windowManager = wm

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.END
        }

        val bubbleBg = GradientDrawable().apply {
            cornerRadius = 22f
            setColor(0xE6111A15.toInt())
            setStroke(2, 0xFF34D399.toInt())
        }

        val speechTv = TextView(this).apply {
            text = idleDialogues[0]
            setTextColor(0xFFECFDF5.toInt())
            textSize = 11f
            maxWidth = 340
            setPadding(14, 8, 14, 8)
            background = bubbleBg
        }
        speechTextView = speechTv

        val leonImg = ImageView(this).apply {
            adjustViewBounds = true
            maxWidth = 176
            maxHeight = 176
            setPadding(8, 6, 8, 2)
        }
        leonImageView = leonImg

        val menuBg = GradientDrawable().apply {
            cornerRadius = 24f
            setColor(0xF2121B16.toInt())
            setStroke(2, 0xFF34D399.toInt())
        }

        val menuBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(14, 12, 14, 12)
            background = menuBg
            visibility = if (menuExpanded) View.VISIBLE else View.GONE
        }
        menuContainer = menuBox

        val statusTv = TextView(this).apply {
            text = "IDLE 25:00 · H:78% ♥72%"
            setTextColor(0xFF6EE7B7.toInt())
            textSize = 11f
            setPadding(0, 0, 0, 8)
        }
        statusTextView = statusTv

        val btnRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }

        val startPauseBtn = Button(this).apply {
            text = "Start"
            textSize = 10f
            minHeight = 0
            minWidth = 0
            setPadding(12, 6, 12, 6)
            setOnClickListener {
                val prefs = PlushiePrefs(this@LeonOverlayService)
                val cur = prefs.loadInitial()
                if (cur.isTimerRunning) {
                    val rem = ((cur.targetEndTimeMs - System.currentTimeMillis()) / 1000L).toInt().coerceAtLeast(1)
                    prefs.save(cur.copy(isTimerRunning = false, remainingSeconds = rem, targetEndTimeMs = 0L))
                    startService(Intent(this@LeonOverlayService, ContainmentService::class.java).apply {
                        action = ContainmentService.ACTION_STOP_LOCK
                    })
                    speechTextView?.text = "Pausing perimeter check."
                } else {
                    val sec = cur.remainingSeconds.coerceAtLeast(60)
                    prefs.save(cur.copy(isTimerRunning = true, remainingSeconds = sec, targetEndTimeMs = System.currentTimeMillis() + sec * 1000L))
                    ContextCompat.startForegroundService(
                        this@LeonOverlayService,
                        Intent(this@LeonOverlayService, ContainmentService::class.java).apply {
                            action = ContainmentService.ACTION_START_LOCK
                            putStringArrayListExtra(ContainmentService.EXTRA_BLOCKED_PKGS, ArrayList(cur.blockedPackages))
                        }
                    )
                    speechTextView?.text = "Focus Lock engaged. Stay sharp."
                }
                updateLeonSpriteAndStatus()
                sendBroadcast(Intent(ACTION_OVERLAY_STATE_CHANGED).setPackage(packageName))
            }
        }
        toggleBtnView = startPauseBtn

        val petBtn = Button(this).apply {
            text = "Pet"
            textSize = 10f
            minHeight = 0
            minWidth = 0
            setPadding(12, 6, 12, 6)
            setOnClickListener {
                val prefs = PlushiePrefs(this@LeonOverlayService)
                val cur = prefs.loadInitial()
                val nextBond = (cur.axolotlAffection + 8).coerceAtMost(100)
                prefs.save(cur.copy(axolotlAffection = nextBond, herbPoints = cur.herbPoints + 2))
                careBoostUntilMs = System.currentTimeMillis() + 4500L
                startService(Intent(this@LeonOverlayService, AxolotlCareService::class.java).apply {
                    action = AxolotlCareService.ACTION_REFRESH_NOW
                })
                speechTextView?.text = "Petted #AX-01! Bond $nextBond%."
                updateLeonSpriteAndStatus()
                sendBroadcast(Intent(ACTION_OVERLAY_STATE_CHANGED).setPackage(packageName))
            }
        }

        val feedBtn = Button(this).apply {
            text = "Feed"
            textSize = 10f
            minHeight = 0
            minWidth = 0
            setPadding(12, 6, 12, 6)
            setOnClickListener {
                val prefs = PlushiePrefs(this@LeonOverlayService)
                val cur = prefs.loadInitial()
                if (cur.herbPoints >= 10) {
                    val nextHunger = (cur.axolotlHunger + 20).coerceAtMost(100)
                    prefs.save(cur.copy(herbPoints = cur.herbPoints - 10, axolotlHunger = nextHunger))
                    careBoostUntilMs = System.currentTimeMillis() + 4500L
                    startService(Intent(this@LeonOverlayService, AxolotlCareService::class.java).apply {
                        action = AxolotlCareService.ACTION_REFRESH_NOW
                    })
                    speechTextView?.text = "Fed herb snack! Fullness $nextHunger%."
                } else {
                    speechTextView?.text = "Need 10 Herbs to feed #AX-01."
                }
                updateLeonSpriteAndStatus()
                sendBroadcast(Intent(ACTION_OVERLAY_STATE_CHANGED).setPackage(packageName))
            }
        }

        val openBtn = Button(this).apply {
            text = "App"
            textSize = 10f
            minHeight = 0
            minWidth = 0
            setPadding(12, 6, 12, 6)
            setOnClickListener {
                val openIntent = Intent(this@LeonOverlayService, MainActivity::class.java).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                }
                startActivity(openIntent)
            }
        }

        val hideBtn = Button(this).apply {
            text = "Hide"
            textSize = 10f
            minHeight = 0
            minWidth = 0
            setPadding(12, 6, 12, 6)
            setOnClickListener {
                val prefs = PlushiePrefs(this@LeonOverlayService)
                val cur = prefs.loadInitial()
                prefs.save(cur.copy(leonOverlayEnabled = false))
                sendBroadcast(Intent(ACTION_OVERLAY_STATE_CHANGED).setPackage(packageName))
                removeOverlay()
                stopSelf()
            }
        }

        btnRow.addView(startPauseBtn)
        btnRow.addView(petBtn)
        btnRow.addView(feedBtn)
        btnRow.addView(openBtn)
        btnRow.addView(hideBtn)

        menuBox.addView(statusTv)
        menuBox.addView(btnRow)

        root.addView(speechTv)
        root.addView(leonImg)
        root.addView(menuBox)

        @Suppress("DEPRECATION")
        val overlayType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            WindowManager.LayoutParams.TYPE_PHONE
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            overlayType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.END
            x = 24
            y = 220
        }

        var downRawX = 0f
        var downRawY = 0f
        var startX = 0
        var startY = 0
        var moved = false

        val gestureListener = View.OnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    downRawX = event.rawX
                    downRawY = event.rawY
                    startX = params.x
                    startY = params.y
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (downRawX - event.rawX).toInt()
                    val dy = (event.rawY - downRawY).toInt()
                    if (abs(dx) > 10 || abs(dy) > 10) moved = true
                    params.x = (startX + dx).coerceAtLeast(0)
                    params.y = (startY + dy).coerceAtLeast(0)
                    try {
                        wm.updateViewLayout(root, params)
                    } catch (_: Exception) {
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!moved) {
                        menuExpanded = !menuExpanded
                        menuContainer?.visibility = if (menuExpanded) View.VISIBLE else View.GONE
                        dialogueIndex += 1
                        updateDialogueText()
                    }
                    true
                }
                else -> false
            }
        }

        leonImg.setOnTouchListener(gestureListener)
        speechTv.setOnTouchListener(gestureListener)

        try {
            wm.addView(root, params)
            floatingView = root
            updateLeonSpriteAndStatus()
        } catch (_: Exception) {
            floatingView = null
        }
    }

    private fun removeOverlay() {
        val v = floatingView ?: return
        try {
            windowManager?.removeView(v)
        } catch (_: Exception) {
        } finally {
            floatingView = null
            menuContainer = null
            speechTextView = null
            statusTextView = null
            toggleBtnView = null
            leonImageView = null
        }
    }

    private fun buildNotification(): Notification {
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
            .setSmallIcon(android.R.drawable.ic_menu_myplaces)
            .setContentTitle("Leon Guard Overlay Active")
            .setContentText("Tap Leon to toggle quick actions · Drag anywhere")
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
                "Leon Guard Overlay",
                NotificationManager.IMPORTANCE_LOW
            )
            nm.createNotificationChannel(ch)
        }
    }

    override fun onDestroy() {
        removeOverlay()
        handler.removeCallbacks(animAndStatusRunnable)
        handler.removeCallbacks(dialogueRunnable)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}

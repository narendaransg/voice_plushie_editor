package com.raccoon.plushie.alarm

import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.AlarmClock
import android.provider.CalendarContract
import android.widget.Toast
import androidx.core.app.NotificationCompat
import com.raccoon.plushie.MainActivity
import com.raccoon.plushie.R
import java.util.Calendar

class TaskAlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val title = intent.getStringExtra(TaskAlarmScheduler.EXTRA_TASK_TITLE) ?: "Save Room Task Due"
        val taskId = intent.getStringExtra(TaskAlarmScheduler.EXTRA_TASK_ID) ?: "task"
        TaskAlarmScheduler.showTaskNotification(context, taskId.hashCode(), title)
    }
}

object TaskAlarmScheduler {
    const val CHANNEL_ID = "raccoon_task_alerts"
    const val CARE_CHANNEL_ID = "raccoon_care_alerts"
    const val EXTRA_TASK_TITLE = "extra_task_title"
    const val EXTRA_TASK_ID = "extra_task_id"

    fun scheduleNotification(context: Context, taskId: String, title: String, triggerAtMs: Long) {
        ensureChannel(context)
        val am = context.getSystemService(Context.ALARM_SERVICE) as? AlarmManager ?: return
        val intent = Intent(context, TaskAlarmReceiver::class.java).apply {
            putExtra(EXTRA_TASK_ID, taskId)
            putExtra(EXTRA_TASK_TITLE, title)
        }
        val pi = PendingIntent.getBroadcast(
            context,
            taskId.hashCode(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val safeTrigger = triggerAtMs.coerceAtLeast(System.currentTimeMillis() + 1000L)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, safeTrigger, pi)
        } else {
            @Suppress("DEPRECATION")
            am.setExact(AlarmManager.RTC_WAKEUP, safeTrigger, pi)
        }
    }

    fun openSystemAlarmSet(context: Context, title: String, triggerAtMs: Long): Boolean {
        val cal = Calendar.getInstance().apply { timeInMillis = triggerAtMs }
        val intent = Intent(AlarmClock.ACTION_SET_ALARM).apply {
            putExtra(AlarmClock.EXTRA_HOUR, cal.get(Calendar.HOUR_OF_DAY))
            putExtra(AlarmClock.EXTRA_MINUTES, cal.get(Calendar.MINUTE))
            putExtra(AlarmClock.EXTRA_MESSAGE, "Save Room: $title")
            putExtra(AlarmClock.EXTRA_SKIP_UI, false)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        return try {
            context.startActivity(intent)
            true
        } catch (_: Exception) {
            Toast.makeText(context, "Clock app unavailable for alarm intent", Toast.LENGTH_SHORT).show()
            false
        }
    }

    fun openCalendarInsert(context: Context, title: String, startMs: Long, accountEmail: String?): Boolean {
        val endMs = startMs + 45 * 60_000L
        val intent = Intent(Intent.ACTION_INSERT).apply {
            data = CalendarContract.Events.CONTENT_URI
            putExtra(CalendarContract.Events.TITLE, title)
            val desc = if (!accountEmail.isNullOrBlank()) {
                "Save Room Plushie task ($accountEmail)"
            } else {
                "Scheduled from Save Room Plushie Attache Case"
            }
            putExtra(CalendarContract.Events.DESCRIPTION, desc)
            putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, startMs)
            putExtra(CalendarContract.EXTRA_EVENT_END_TIME, endMs)
            if (!accountEmail.isNullOrBlank()) {
                putExtra(Intent.EXTRA_EMAIL, accountEmail)
            }
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        return try {
            context.startActivity(intent)
            true
        } catch (_: Exception) {
            Toast.makeText(context, "No calendar app available to insert event", Toast.LENGTH_SHORT).show()
            false
        }
    }

    fun showTaskNotification(context: Context, notifId: Int, title: String) {
        ensureChannel(context)
        val openIntent = Intent(context, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        val pi = PendingIntent.getActivity(
            context,
            notifId,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notif = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_popup_reminder)
            .setContentTitle("Save Room Scheduled Task")
            .setContentText(title)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()

        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(notifId, notif)
    }

    fun showCareNotification(context: Context, message: String) {
        ensureCareChannel(context)
        val openIntent = Intent(context, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        val pi = PendingIntent.getActivity(
            context,
            7701,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notif = NotificationCompat.Builder(context, CARE_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.star_on)
            .setContentTitle("Specimen #AX-01 Care Alert")
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()

        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(7701, notif)
    }

    private fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val ch = NotificationChannel(
                CHANNEL_ID,
                context.getString(R.string.task_channel_name),
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = context.getString(R.string.task_channel_desc)
            }
            nm.createNotificationChannel(ch)
        }
    }

    private fun ensureCareChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val ch = NotificationChannel(
                CARE_CHANNEL_ID,
                context.getString(R.string.care_channel_name),
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = context.getString(R.string.care_channel_desc)
            }
            nm.createNotificationChannel(ch)
        }
    }
}

package com.raccoon.plushie.sensors

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import kotlin.math.sqrt

class SensorRig(
    context: Context,
    private val onShakeDetected: () -> Unit,
    private val onFaceDownChanged: (Boolean) -> Unit,
    private val onLowLightChanged: (Boolean) -> Unit,
    private val onTiltChanged: (Float, Float) -> Unit
) : SensorEventListener {

    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val accelSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
    private val lightSensor = sensorManager.getDefaultSensor(Sensor.TYPE_LIGHT)
    private val proxSensor = sensorManager.getDefaultSensor(Sensor.TYPE_PROXIMITY)

    private var lastShakeTimeMs = 0L
    private var lastFaceDown = false
    private var lastLowLight = false
    private var pitch = 0f
    private var roll = 0f

    fun start() {
        accelSensor?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI) }
        gyroSensor?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI) }
        lightSensor?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL) }
        proxSensor?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL) }
    }

    fun stop() {
        sensorManager.unregisterListener(this)
    }

    override fun onSensorChanged(event: SensorEvent) {
        when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> {
                val x = event.values[0]
                val y = event.values[1]
                val z = event.values[2]
                val gForce = sqrt((x * x + y * y + z * z).toDouble()) / SensorManager.GRAVITY_EARTH
                val now = System.currentTimeMillis()
                if (gForce > 2.35 && now - lastShakeTimeMs > 1400L) {
                    lastShakeTimeMs = now
                    onShakeDetected()
                }
                val faceDown = z < -7.5f
                if (faceDown != lastFaceDown) {
                    lastFaceDown = faceDown
                    onFaceDownChanged(faceDown)
                }
            }

            Sensor.TYPE_GYROSCOPE -> {
                roll = (roll + event.values[0] * 0.12f).coerceIn(-1f, 1f)
                pitch = (pitch + event.values[1] * 0.12f).coerceIn(-1f, 1f)
                onTiltChanged(pitch, roll)
            }

            Sensor.TYPE_LIGHT -> {
                val lux = event.values[0]
                val lowLight = lux < 12f
                if (lowLight != lastLowLight) {
                    lastLowLight = lowLight
                    onLowLightChanged(lowLight)
                }
            }

            Sensor.TYPE_PROXIMITY -> {
                val maxRange = event.sensor.maximumRange
                val near = event.values[0] < maxRange && event.values[0] < 3f
                if (near && !lastFaceDown) {
                    lastFaceDown = true
                    onFaceDownChanged(true)
                }
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
}

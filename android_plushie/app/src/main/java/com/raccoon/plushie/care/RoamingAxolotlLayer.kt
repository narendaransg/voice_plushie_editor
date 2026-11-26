package com.raccoon.plushie.care

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import com.raccoon.plushie.R
import com.raccoon.plushie.ui.SpriteStripFrame
import com.raccoon.plushie.ui.theme.ShinyAxolotlCyan
import kotlinx.coroutines.delay
import kotlin.math.hypot
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.random.Random

@Composable
fun RoamingAxolotlScreenLayer(
    enabled: Boolean,
    hunger: Int,
    affection: Int,
    tiltX: Float,
    tiltY: Float,
    pointerTargetPx: Offset?,
    onPetAxolotl: () -> Unit
) {
    if (!enabled) return

    val density = LocalDensity.current
    var isPetting by remember { mutableStateOf(false) }
    var isResting by remember { mutableStateOf(false) }
    var facingLeft by remember { mutableStateOf(false) }
    var posX by remember { mutableFloatStateOf(160f) }
    var posY by remember { mutableFloatStateOf(260f) }
    var goalX by remember { mutableFloatStateOf(420f) }
    var goalY by remember { mutableFloatStateOf(520f) }
    var tickCount by remember { mutableIntStateOf(0) }

    LaunchedEffect(isPetting) {
        if (isPetting) {
            delay(1400L)
            isPetting = false
        }
    }

    BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
        val spriteSizeDp = 96.dp
        val maxXPx = with(density) { (maxWidth - spriteSizeDp).coerceAtLeast(24.dp).toPx() }
        val maxYPx = with(density) { (maxHeight - spriteSizeDp).coerceAtLeast(48.dp).toPx() }
        val halfSpritePx = with(density) { (spriteSizeDp / 2).toPx() }

        LaunchedEffect(maxXPx, maxYPx) {
            while (true) {
                delay(32L)
                tickCount += 1

                val followFinger = pointerTargetPx != null && (tickCount % 320) < 170
                if (followFinger && pointerTargetPx != null) {
                    isResting = false
                    goalX = (pointerTargetPx.x - halfSpritePx).coerceIn(0f, maxXPx)
                    goalY = (pointerTargetPx.y - halfSpritePx).coerceIn(0f, maxYPx)
                } else if (tickCount % 220 == 0) {
                    isResting = !isResting
                    if (!isResting) {
                        goalX = Random.nextFloat() * maxXPx
                        goalY = Random.nextFloat() * maxYPx
                    }
                }

                if (!isResting) {
                    val dx = goalX - posX + tiltX * 4f
                    val dy = goalY - posY + tiltY * 4f
                    val dist = hypot(dx, dy)
                    if (dist > 6f) {
                        facingLeft = dx < -1.5f
                        val speed = if (followFinger) 6.5f else 3.2f
                        posX = (posX + (dx / dist) * speed).coerceIn(0f, maxXPx)
                        posY = (posY + (dy / dist) * speed).coerceIn(0f, maxYPx)
                    } else if (!followFinger) {
                        isResting = true
                    }
                }
            }
        }

        val bobOffset = if (isResting) 0f else (sin(tickCount * 0.14) * 5.0).toFloat()

        Box(
            modifier = Modifier
                .offset { IntOffset(posX.roundToInt(), (posY + bobOffset).roundToInt()) }
                .size(spriteSizeDp)
                .graphicsLayer {
                    scaleX = when {
                        isPetting -> 1.16f
                        facingLeft -> -1f
                        else -> 1f
                    }
                    scaleY = if (isPetting) 1.16f else 1f
                    rotationZ = if (isResting) 0f else (sin(tickCount * 0.1) * 5.0).toFloat()
                }
                .clickable {
                    isPetting = true
                    isResting = false
                    onPetAxolotl()
                },
            contentAlignment = Alignment.Center
        ) {
            when {
                isPetting -> SpriteStripFrame(
                    sheetResId = R.drawable.sheet_axolotl_pet,
                    frameCount = 4,
                    frameDurationMs = 250L,
                    modifier = Modifier.fillMaxSize(),
                    contentDescription = "Petted Shiny Axolotl"
                )
                isResting && hunger < 45 -> SpriteStripFrame(
                    sheetResId = R.drawable.sheet_axolotl_hungry,
                    frameCount = 4,
                    frameDurationMs = 460L,
                    modifier = Modifier.fillMaxSize(),
                    contentDescription = "Hungry Resting Axolotl"
                )
                isResting -> SpriteStripFrame(
                    sheetResId = R.drawable.sheet_axolotl_idle,
                    frameCount = 4,
                    frameDurationMs = 440L,
                    modifier = Modifier.fillMaxSize(),
                    contentDescription = "Resting Shiny Axolotl"
                )
                else -> SpriteStripFrame(
                    sheetResId = R.drawable.sheet_axolotl_swim,
                    frameCount = 6,
                    frameDurationMs = 175L,
                    modifier = Modifier.fillMaxSize(),
                    contentDescription = "Swimming Shiny Axolotl"
                )
            }
        }
    }
}

@Composable
fun AxolotlCareCard(
    hunger: Int,
    affection: Int,
    petCountToday: Int,
    roamingEnabled: Boolean,
    careAlertsEnabled: Boolean,
    herbPoints: Int,
    onToggleRoaming: () -> Unit,
    onToggleCareAlerts: () -> Unit,
    onPetAxolotl: () -> Unit,
    onFeedAxolotl: () -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.74f)),
        border = BorderStroke(1.dp, ShinyAxolotlCyan.copy(alpha = 0.65f)),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(44.dp)
                            .clip(RoundedCornerShape(10.dp))
                            .background(Color(0x880A1922))
                    ) {
                        Image(
                            painter = painterResource(id = R.drawable.axolotl_shiny_plush),
                            contentDescription = "Specimen AX-01",
                            modifier = Modifier.fillMaxSize(),
                            contentScale = ContentScale.Crop
                        )
                    }
                    Column {
                        Text(
                            text = "AXOLOTL CARE & ROAMING TANK",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold,
                            color = ShinyAxolotlCyan
                        )
                        Text(
                            text = "Fullness: $hunger% · Bond: $affection% · Pets: $petCountToday",
                            style = MaterialTheme.typography.labelSmall
                        )
                    }
                }
            }

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onPetAxolotl) {
                    Text("Pet (+Bond)")
                }
                OutlinedButton(onClick = onFeedAxolotl) {
                    Text("Feed (-10 Herbs)")
                }
            }

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onToggleRoaming) {
                    Text(if (roamingEnabled) "Swim Roam: ON" else "Swim Roam: OFF")
                }
                OutlinedButton(onClick = onToggleCareAlerts) {
                    Text(if (careAlertsEnabled) "Care Alerts: ON" else "Care Alerts: OFF")
                }
            }

            Text(
                text = "Herbs: $herbPoints pts · Swims free with no box, rests on UI blocks, and follows your finger occasionally.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.78f)
            )
        }
    }
}

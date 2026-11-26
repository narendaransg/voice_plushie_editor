package com.raccoon.plushie.ui

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.annotation.DrawableRes
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.raccoon.plushie.R
import com.raccoon.plushie.ui.theme.AmberNightOps
import com.raccoon.plushie.ui.theme.HerbGreen
import com.raccoon.plushie.ui.theme.ShinyAxolotlCyan
import kotlinx.coroutines.delay

data class InstalledLauncherApp(
    val label: String,
    val packageName: String
)

fun queryLauncherApps(context: Context): List<InstalledLauncherApp> {
    val pm = context.packageManager
    val intent = Intent(Intent.ACTION_MAIN, null).apply {
        addCategory(Intent.CATEGORY_LAUNCHER)
    }
    @Suppress("DEPRECATION")
    val resolved = pm.queryIntentActivities(intent, 0)
    return resolved
        .mapNotNull { info ->
            val pkg = info.activityInfo?.packageName ?: return@mapNotNull null
            if (pkg == context.packageName) return@mapNotNull null
            val title = info.loadLabel(pm)?.toString()?.trim().orEmpty().ifBlank { pkg }
            InstalledLauncherApp(label = title, packageName = pkg)
        }
        .distinctBy { it.packageName }
        .sortedBy { it.label.lowercase() }
}

@Composable
fun SpriteStripFrame(
    @DrawableRes sheetResId: Int,
    frameCount: Int,
    frameDurationMs: Long,
    modifier: Modifier = Modifier,
    contentDescription: String
) {
    val context = LocalContext.current
    var frameIndex by remember { mutableIntStateOf(0) }

    val fullBitmap = remember(sheetResId) {
        try {
            BitmapFactory.decodeResource(context.resources, sheetResId)
        } catch (_: Exception) {
            null
        }
    }

    LaunchedEffect(fullBitmap, frameCount, frameDurationMs) {
        if (fullBitmap != null && frameCount > 1) {
            while (true) {
                delay(frameDurationMs)
                frameIndex = (frameIndex + 1) % frameCount
            }
        }
    }

    val croppedImageBitmap = remember(fullBitmap, frameIndex, frameCount) {
        val bmp = fullBitmap ?: return@remember null
        if (bmp.width <= 0 || bmp.height <= 0 || frameCount <= 0) return@remember null
        val frameW = (bmp.width / frameCount).coerceAtLeast(1)
        val safeX = (frameIndex * frameW).coerceIn(0, (bmp.width - 1).coerceAtLeast(0))
        val actualW = frameW.coerceAtMost((bmp.width - safeX).coerceAtLeast(1))
        val slice: Bitmap = Bitmap.createBitmap(bmp, safeX, 0, actualW, bmp.height)
        slice.asImageBitmap()
    }

    if (croppedImageBitmap != null) {
        Image(
            bitmap = croppedImageBitmap,
            contentDescription = contentDescription,
            modifier = modifier,
            contentScale = ContentScale.Fit
        )
    } else {
        Image(
            painter = painterResource(id = R.drawable.axolotl_shiny_plush),
            contentDescription = contentDescription,
            modifier = modifier,
            contentScale = ContentScale.Fit
        )
    }
}

@Composable
fun PlushiePocketTankCard(
    shinyAxolotlUnlocked: Boolean,
    isTimerRunning: Boolean,
    tiltX: Float,
    tiltY: Float,
    lowLightNightOps: Boolean,
    herbPoints: Int,
    firstAidSpraysLeft: Int
,
    isRoamingOutside: Boolean = false
) {
    val borderColor = if (shinyAxolotlUnlocked) ShinyAxolotlCyan else HerbGreen
    val tankOverlayBrush = Brush.verticalGradient(
        colors = listOf(Color(0x9906131C), Color(0xCC091A16))
    )

    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, borderColor),
        modifier = Modifier.fillMaxWidth()
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(148.dp)
        ) {
            Image(
                painter = painterResource(id = R.drawable.bg_pocket_tank),
                contentDescription = "Pocket Tank Backdrop",
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop
            )
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(tankOverlayBrush)
            )
            Row(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(116.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(Color(0x55000000))
                        .graphicsLayer {
                            rotationX = (tiltY * 12f).coerceIn(-14f, 14f)
                            rotationY = (tiltX * 12f).coerceIn(-14f, 14f)
                        },
                    contentAlignment = Alignment.Center
                ) {
                    if (isRoamingOutside) {
                        Text(
                            text = "OUT SWIMMING\n(Tap on screen)",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                            color = ShinyAxolotlCyan
                        )
                    } else if (shinyAxolotlUnlocked) {
                        SpriteStripFrame(
                            sheetResId = R.drawable.sheet_axolotl_idle,
                            frameCount = 4,
                            frameDurationMs = 420L,
                            modifier = Modifier.fillMaxSize(),
                            contentDescription = "Shiny Blue Axolotl Animation"
                        )
                    } else {
                        SpriteStripFrame(
                            sheetResId = R.drawable.sheet_leon_cheer,
                            frameCount = 3,
                            frameDurationMs = 520L,
                            modifier = Modifier.fillMaxSize(),
                            contentDescription = "Chibi Tactical Plushie Animation"
                        )
                    }
                }

                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = if (shinyAxolotlUnlocked) {
                            "SHINY AXOLOTL (#AX-01) IN TANK"
                        } else {
                            "SAVE ROOM CO-PILOT GUARD"
                        },
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = if (lowLightNightOps) AmberNightOps else borderColor
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = if (isTimerRunning) {
                            "Study shield active — holding the perimeter."
                        } else {
                            "Tap Start Save Room or flip face-down to lock in."
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = Color(0xFFF3F4F6)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Image(
                                painter = painterResource(id = R.drawable.herb_cluster_icon),
                                contentDescription = "Herbs",
                                modifier = Modifier.size(22.dp)
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Text(
                                text = "$herbPoints",
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold,
                                color = HerbGreen
                            )
                        }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Image(
                                painter = painterResource(id = R.drawable.first_aid_spray_icon),
                                contentDescription = "First Aid Spray",
                                modifier = Modifier.size(22.dp)
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Text(
                                text = "x$firstAidSpraysLeft",
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold,
                                color = Color(0xFFFCA5A5)
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun InstalledAppPickerDialog(
    alreadyBlocked: Set<String>,
    onDismiss: () -> Unit,
    onSelectPackage: (String) -> Unit
) {
    val context = LocalContext.current
    var query by remember { mutableStateOf("") }
    val apps = remember { queryLauncherApps(context) }
    val filtered = remember(apps, query) {
        if (query.isBlank()) apps
        else apps.filter {
            it.label.contains(query, ignoreCase = true) ||
                it.packageName.contains(query, ignoreCase = true)
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Select App to Block") },
        text = {
            Column(modifier = Modifier.fillMaxWidth()) {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("Search installed apps...") }
                )
                Spacer(modifier = Modifier.height(8.dp))
                LazyColumn(modifier = Modifier.height(260.dp)) {
                    items(filtered, key = { it.packageName }) { app ->
                        val isBlocked = app.packageName in alreadyBlocked
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(app.label, fontWeight = FontWeight.SemiBold)
                                Text(
                                    app.packageName,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.65f)
                                )
                            }
                            if (isBlocked) {
                                Text("Blocked", style = MaterialTheme.typography.labelSmall, color = ShinyAxolotlCyan)
                            } else {
                                Button(onClick = { onSelectPackage(app.packageName) }) {
                                    Text("Add")
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            OutlinedButton(onClick = onDismiss) {
                Text("Close")
            }
        }
    )
}

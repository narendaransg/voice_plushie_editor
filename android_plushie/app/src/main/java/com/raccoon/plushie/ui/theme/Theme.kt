package com.raccoon.plushie.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val SafeRoomBg = Color(0xFF0C110F)
val SafeRoomSurface = Color(0xFF151E19)
val HerbGreen = Color(0xFF34D399)
val HerbYellow = Color(0xFFFBBF24)
val HerbRed = Color(0xFFF87171)
val ShinyAxolotlCyan = Color(0xFF38BDF8)
val TerminalPhosphor = Color(0xFF4ADE80)
val AmberNightOps = Color(0xFFF59E0B)

private val BiohazardScheme = darkColorScheme(
    primary = HerbGreen,
    secondary = ShinyAxolotlCyan,
    background = SafeRoomBg,
    surface = SafeRoomSurface,
    onPrimary = Color(0xFF052E16),
    onSecondary = Color(0xFF082F49),
    onBackground = Color(0xFFECFDF5),
    onSurface = Color(0xFFE5E7EB)
)

private val TerminalScheme = darkColorScheme(
    primary = TerminalPhosphor,
    secondary = HerbGreen,
    background = Color(0xFF050806),
    surface = Color(0xFF0A120D),
    onPrimary = Color(0xFF052E16),
    onSecondary = Color(0xFF052E16),
    onBackground = TerminalPhosphor,
    onSurface = TerminalPhosphor
)

@Composable
fun RaccoonPlushieTheme(
    terminalMode: Boolean,
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = if (terminalMode) TerminalScheme else BiohazardScheme,
        content = content
    )
}

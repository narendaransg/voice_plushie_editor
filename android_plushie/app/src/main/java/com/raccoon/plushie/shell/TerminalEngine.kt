package com.raccoon.plushie.shell

import android.content.Context
import android.content.Intent
import java.io.File

data class ShellCommandResult(
    val output: String,
    val startPomodoroMinutes: Int? = null,
    val unlockShinyAxolotl: Boolean = false,
    val toggleTermTheme: Boolean = false,
    val triggerStaReport: Boolean = false,
    val mixHerbs: Boolean = false,
    val launchTermuxCommand: String? = null
)

object TerminalEngine {

    fun isTermuxInstalled(context: Context): Boolean {
        return try {
            context.packageManager.getPackageInfo("com.termux", 0)
            true
        } catch (_: Exception) {
            false
        }
    }

    fun runTermuxIntent(context: Context, command: String): Boolean {
        if (!isTermuxInstalled(context)) return false
        return try {
            val intent = Intent("com.termux.RUN_COMMAND").apply {
                setClassName("com.termux", "com.termux.app.RunCommandService")
                putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/bash")
                putExtra("com.termux.RUN_COMMAND_ARGUMENTS", arrayOf("-lc", command))
                putExtra("com.termux.RUN_COMMAND_BACKGROUND", false)
            }
            context.startService(intent)
            true
        } catch (_: Exception) {
            false
        }
    }

    fun execute(context: Context, rawInput: String, workDir: File): ShellCommandResult {
        val cmd = rawInput.trim()
        if (cmd.isEmpty()) return ShellCommandResult("")

        val lower = cmd.lowercase()
        return when {
            lower == "help" -> ShellCommandResult(
                """
                Save Room Shell + Linux/RE/VLSI/Axolotl Commands:
                  saferoom [mins]   Start Pomodoro containment (default 25m)
                  scan              Check Instagram & focus status
                  sta               Run VLSI Static Timing Analysis focus check
                  herb mix          Combine herbs into stamina points
                  spawn axolotl     Summon Specimen #AX-01 (Shiny Blue Axolotl)
                  tty               Toggle green/amber terminal theme
                  termux <cmd>      Bridge command into Termux app if installed
                  sh <linux_cmd>    Run real /system/bin/sh command (e.g. ls, uname -a, ps)
                """.trimIndent()
            )

            lower == "saferoom" || lower.startsWith("saferoom ") -> {
                val mins = lower.removePrefix("saferoom").trim().toIntOrNull()?.coerceIn(5, 90) ?: 25
                ShellCommandResult(
                    output = "[SAVEROOM] Ink ribbon inked. Starting ${mins}m containment timer.",
                    startPomodoroMinutes = mins
                )
            }

            lower == "scan" || lower == "ps-threat" -> ShellCommandResult(
                """
                [SCAN] Threat monitor armed: com.instagram.android
                [SCAN] Sensor hooks: ACCEL, GYRO, LIGHT, PROXIMITY active.
                """.trimIndent()
            )

            lower == "sta" -> ShellCommandResult(
                output = "[STA] clock: clk_study (50MHz) | WNS: +0.42ns | TNS: 0.00ns | Slack: MET",
                triggerStaReport = true
            )

            lower == "herb mix" -> ShellCommandResult(
                output = "[HERB] Mixed Green + Red + Yellow essence -> +10 Stamina/Herb points.",
                mixHerbs = true
            )

            lower == "spawn axolotl" || lower.contains("shiny") -> ShellCommandResult(
                output = "[UMBRELLA-LAB] Specimen #AX-01 (Shiny Blue Axolotl, 1/1200) materialized!",
                unlockShinyAxolotl = true
            )

            lower == "tty" || lower == "sudo su" -> ShellCommandResult(
                output = "[TTY] Switching Save Room display to phosphor shell mode.",
                toggleTermTheme = true
            )

            lower.startsWith("termux ") -> {
                val inner = cmd.substringAfter("termux ").trim()
                val launched = runTermuxIntent(context, inner)
                if (launched) {
                    ShellCommandResult("[TERMUX] Dispatched via com.termux.RUN_COMMAND: $inner", launchTermuxCommand = inner)
                } else {
                    ShellCommandResult("[TERMUX] Termux not detected or RUN_COMMAND blocked. Install Termux or use 'sh <cmd>'.")
                }
            }

            else -> {
                val shellCmd = if (lower.startsWith("sh ")) cmd.substringAfter("sh ").trim() else cmd
                runSystemShell(shellCmd, workDir)
            }
        }
    }

    private fun runSystemShell(command: String, workDir: File): ShellCommandResult {
        return try {
            val process = ProcessBuilder("/system/bin/sh", "-c", command)
                .directory(workDir)
                .redirectErrorStream(true)
                .start()
            val out = process.inputStream.bufferedReader().use { it.readText() }.trim()
            val code = process.waitFor()
            ShellCommandResult(if (out.isBlank()) "[exit $code]" else "$out\n[exit $code]")
        } catch (e: Exception) {
            ShellCommandResult("[sh error] ${e.message}")
        }
    }
}

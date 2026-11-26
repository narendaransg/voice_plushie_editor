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
    val triggerMerchant: Boolean = false,
    val triggerMinecraftEgg: Boolean = false,
    val mixHerbs: Boolean = false,
    val newTodoTitle: String? = null,
    val blockPkgName: String? = null,
    val unblockPkgName: String? = null,
    val saveApkToRepo: Boolean = false,
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
                Save Room Shell + RE / Linux / Minecraft / VLSI Commands:
                  saferoom [mins]   Start Pomodoro containment (default 25m)
                  scan              Check blocked apps & focus status
                  block <pkg>       Add package to containment shield
                  unblock <pkg>     Remove package from shield
                  todo <task>       Add task to Attache Case to-do list
                  save-apk          Stage APK export path / log repo release note
                  sta               Run VLSI Static Timing Analysis focus check
                  synth             Run quick ASIC/RTL focus synthesis check
                  herb mix          Combine herbs into stamina points
                  spawn axolotl     Summon Specimen #AX-01 (Shiny Blue Axolotl)
                  merchant          Summon the Save Room Merchant
                  nether            Trigger Minecraft Redstone/Nether easter egg
                  dmesg             Print Save Room kernel/sensor boot log
                  tty               Toggle green/amber terminal theme
                  termux <cmd>      Bridge command into Termux app if installed
                  sh <linux_cmd>    Run real /system/bin/sh command
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
                "[SCAN] Shield active on configured packages. Sensors ACCEL/GYRO/LIGHT/PROX armed."
            )

            lower.startsWith("block ") -> {
                val pkg = cmd.substringAfter("block ").trim()
                if (pkg.isEmpty()) ShellCommandResult("[BLOCK] Usage: block <com.package.name>")
                else ShellCommandResult("[BLOCK] Added '$pkg' to Bio-Shield block list.", blockPkgName = pkg)
            }

            lower.startsWith("unblock ") -> {
                val pkg = cmd.substringAfter("unblock ").trim()
                if (pkg.isEmpty()) ShellCommandResult("[UNBLOCK] Usage: unblock <com.package.name>")
                else ShellCommandResult("[UNBLOCK] Removed '$pkg' from Bio-Shield block list.", unblockPkgName = pkg)
            }

            lower.startsWith("todo ") -> {
                val title = cmd.substringAfter("todo ").trim()
                if (title.isEmpty()) ShellCommandResult("[TODO] Usage: todo <task description>")
                else ShellCommandResult("[TODO] Added '$title' to Attache Case.", newTodoTitle = title)
            }

            lower == "save-apk" || lower == "repo-apk" -> ShellCommandResult(
                output = "[REPO-APK] Run on WSL2 laptop: mkdir -p release && cp app/build/outputs/apk/debug/app-debug.apk release/SaveRoomPlushie-debug.apk",
                saveApkToRepo = true
            )

            lower == "sta" -> ShellCommandResult(
                output = "[STA] clk: clk_study (50MHz) | WNS: +0.42ns | TNS: 0.00ns | Slack: MET",
                triggerStaReport = true
            )

            lower == "synth" -> ShellCommandResult(
                output = "[GENUS/YOSYS] Cell area: 14.2k um^2 | Power: 1.18mW | Doomscroll FF: 0"
            )

            lower == "herb mix" -> ShellCommandResult(
                output = "[HERB] Mixed Green + Red + Yellow essence -> +10 Stamina/Herb points.",
                mixHerbs = true
            )

            lower == "spawn axolotl" || lower.contains("shiny") -> ShellCommandResult(
                output = "[UMBRELLA-LAB] Specimen #AX-01 (Shiny Blue Axolotl, 1/1200) materialized!",
                unlockShinyAxolotl = true
            )

            lower == "merchant" -> ShellCommandResult(
                output = "[MERCHANT] 'Hehehe... got somethin' that might interest ya! (+15 Herb pts)'",
                triggerMerchant = true
            )

            lower == "nether" || lower == "redstone" -> ShellCommandResult(
                output = "[MINECRAFT] Obsidian frame lit! Shiny Axolotl bucket + 64 Redstone dust synced.",
                triggerMinecraftEgg = true
            )

            lower == "dmesg" -> ShellCommandResult(
                """
                [    0.000] raccoon-os 6.6-save-room initializing sensors
                [    0.112] axolotl_lab: specimen #AX-01 shimmer bus online
                [    0.240] bioshield: watching target packages during study lock
                """.trimIndent()
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

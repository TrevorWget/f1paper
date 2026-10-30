<#
.SYNOPSIS
    Registers a daily Windows Task Scheduler job that runs `f1paper run`.

.PARAMETER TaskName
    Name of the scheduled task (default: F1PaperDailyRefresh).

.PARAMETER Time
    Daily run time in HH:MM 24-hour format (default: 09:00).
#>
param(
    [string]$TaskName = "F1PaperDailyRefresh",
    [string]$Time = "09:00"
)

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
    Write-Error "Could not find 'python' or 'py' on PATH. Install Python and ensure f1paper is installed (pip install -e .) before running this script."
    exit 1
}

$action = New-ScheduledTaskAction -Execute $pythonCmd.Source -Argument "-m f1paper.cli run"
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Refreshes the F1 race-weekend desktop wallpaper (f1paper)" -Force | Out-Null

Write-Host "Installed scheduled task '$TaskName' to run daily at $Time."
Write-Host "You can trigger it manually any time with: schtasks /Run /TN `"$TaskName`""

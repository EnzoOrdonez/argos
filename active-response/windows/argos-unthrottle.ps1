# ARGOS active-response (Windows) - restaura la prioridad Normal del proceso. param: pid.
$ErrorActionPreference = "SilentlyContinue"

$raw = [Console]::In.ReadToEnd()
$procId = ($raw | ConvertFrom-Json).parameters.alert.data.argos.pid
if (-not $procId) { Write-Output "argos-unthrottle: sin pid -> no-op"; exit 0 }

$proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
if ($proc) {
    $proc.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::Normal
    Write-Output "argos-unthrottle: pid $procId -> prioridad Normal"
}

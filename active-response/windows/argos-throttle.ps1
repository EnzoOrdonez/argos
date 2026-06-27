# ARGOS active-response (Windows) - baja la prioridad del proceso ofensor para acotar
# el dano durante la espera HITL (ADR-0006 Sit.B). param: pid. Corre como SYSTEM.
$ErrorActionPreference = "SilentlyContinue"

$raw = [Console]::In.ReadToEnd()
$procId = ($raw | ConvertFrom-Json).parameters.alert.data.argos.pid
if (-not $procId) { Write-Output "argos-throttle: sin pid -> no-op"; exit 0 }

$proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
if ($proc) {
    $proc.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::Idle
    Write-Output "argos-throttle: pid $procId -> prioridad Idle"
} else {
    Write-Output "argos-throttle: pid $procId no encontrado"
}

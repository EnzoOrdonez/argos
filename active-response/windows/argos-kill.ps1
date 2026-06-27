# ARGOS active-response (Windows) - mata el proceso ofensor (Stop-Process -Force).
# param: pid. Reversible en el sentido de ADR-0012 §7.3 (el servicio se relanza).
$ErrorActionPreference = "SilentlyContinue"

$raw = [Console]::In.ReadToEnd()
$procId = ($raw | ConvertFrom-Json).parameters.alert.data.argos.pid
if (-not $procId) { Write-Output "argos-kill: sin pid -> no-op"; exit 0 }

Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
Write-Output "argos-kill: pid $procId terminado"

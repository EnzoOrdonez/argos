# ARGOS active-response (Windows) - snapshot demo-safe: copia el dir protegido.
# NO es VSS real (ADR-0012 §2.6). Origen: $env:ARGOS_SNAPSHOT_DIR. Destino: $env:ARGOS_SNAPSHOT_DEST.
$ErrorActionPreference = "SilentlyContinue"

[Console]::In.ReadToEnd() | Out-Null
$src  = if ($env:ARGOS_SNAPSHOT_DIR)  { $env:ARGOS_SNAPSHOT_DIR }  else { "C:\Users\victim\Documents" }
$dest = if ($env:ARGOS_SNAPSHOT_DEST) { $env:ARGOS_SNAPSHOT_DEST } else { "C:\ProgramData\argos-snapshots" }
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$out = Join-Path $dest "argos-snapshot-$stamp"

New-Item -ItemType Directory -Force -Path $out | Out-Null
Copy-Item -Path $src -Destination $out -Recurse -Force
Write-Output "argos-snapshot: $src -> $out"

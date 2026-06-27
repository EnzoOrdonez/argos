# ARGOS active-response (Windows) - aisla la victima con netsh advfirewall, PERO
# permite el canal con el Wazuh manager (1514/1515). Sin esa regla allow el manager
# no podria revertir ni confirmar: auto-brick. La regla allow se crea ANTES del block-all.
#
# Interfaz Wazuh AR: JSON de wazuh-execd por stdin (.command = add|delete). Lo invoca el
# SOAR con el comando "argos-isolate". MANAGER_IP: $env:ARGOS_MANAGER_IP o
# C:\Program Files (x86)\ossec-agent\argos-ar.conf. Corre como SYSTEM (agente Wazuh).
$ErrorActionPreference = "Stop"

$raw = [Console]::In.ReadToEnd()
try { $command = ($raw | ConvertFrom-Json).command } catch { $command = "add" }
if (-not $command) { $command = "add" }

$managerIp = $env:ARGOS_MANAGER_IP
$conf = "C:\Program Files (x86)\ossec-agent\argos-ar.conf"
if (-not $managerIp -and (Test-Path $conf)) {
    $line = Get-Content $conf | Where-Object { $_ -match '^MANAGER_IP=' } | Select-Object -First 1
    $managerIp = $line -replace '^MANAGER_IP=', ''
}

function Invoke-Isolate {
    if (-not $managerIp) {
        Write-Error "argos-isolate: MANAGER_IP sin configurar -> abort (evita auto-brick)"
        exit 1
    }
    # --- ALLOW del manager PRIMERO (1514/1515) ---
    netsh advfirewall firewall add rule name="argos-allow-manager-out" dir=out action=allow protocol=TCP remoteip=$managerIp remoteport=1514,1515 | Out-Null
    netsh advfirewall firewall add rule name="argos-allow-manager-in"  dir=in  action=allow protocol=TCP remoteip=$managerIp localport=1514,1515  | Out-Null
    # --- BLOCK-ALL DESPUES: politica por defecto bloquea; las reglas allow tienen prioridad ---
    netsh advfirewall set allprofiles firewallpolicy blockinbound,blockoutbound | Out-Null
    Write-Output "argos-isolate: victima aislada; manager $managerIp permitido (1514/1515)"
}

function Invoke-Unisolate {
    netsh advfirewall set allprofiles firewallpolicy blockinbound,allowoutbound | Out-Null
    netsh advfirewall firewall delete rule name="argos-allow-manager-out" | Out-Null
    netsh advfirewall firewall delete rule name="argos-allow-manager-in"  | Out-Null
    Write-Output "argos-isolate: aislamiento revertido"
}

if ($command -eq "delete") { Invoke-Unisolate } else { Invoke-Isolate }

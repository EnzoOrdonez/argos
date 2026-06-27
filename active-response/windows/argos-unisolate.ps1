# ARGOS active-response (Windows) - revierte argos-isolate: restaura la politica del
# firewall y borra las reglas allow del manager. Lo invoca el SOAR con "argos-unisolate".
$ErrorActionPreference = "SilentlyContinue"

[Console]::In.ReadToEnd() | Out-Null
netsh advfirewall set allprofiles firewallpolicy blockinbound,allowoutbound | Out-Null
netsh advfirewall firewall delete rule name="argos-allow-manager-out" | Out-Null
netsh advfirewall firewall delete rule name="argos-allow-manager-in"  | Out-Null
Write-Output "argos-unisolate: aislamiento removido"

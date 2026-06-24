# Matriz de Validación — P3 (Angeles Castillo)

Cobertura de los casos de uso que corresponden a mi alcance (Layer 1 +
Layer 3 + simuladores). UC-03 y UC-05 se mencionan en el README de
`detection/` como milestones de Gate 2-3 pero no están en la lista
explícita de "casos de uso que debo cubrir" del manual — se incluyen
aquí solo como referencia de las reglas que ya las cubren parcialmente.

| UC | Vector | Archivo/script P3 | Regla Sigma/Wazuh | MITRE | Capa | Resultado esperado | Evidencia para demo | Depende de |
|----|--------|--------------------|--------------------|-------|------|---------------------|----------------------|------------|
| UC-01 | LockBit-like (cifrado simulado en sandbox) | `detection/simulators/uc01_lockbit_like.py` | `ransomware/vssadmin_delete_shadows.yml`, `ransomware/high_entropy_writes.yml`, `ransomware/ransom_note_drop.yml`, `discovery/file_enumeration_powershell.yml`, `defense-evasion/stop_service_wazuh_agent.yml` | T1486, T1490, T1083, T1562.001 | Layer 1 | Alertas Sigma/Wazuh disparan para cada técnica antes de "cifrado" simulado; cero archivos reales tocados | Logs de alertas + capturas de Wazuh dashboard + `_simulated_events.log` del sandbox | Lab de P4 para ejecutar contra víctima real (el simulador en sí ya corre 100% local) |
| UC-02 | Canary path (toque de archivo cebo) | `canary-generator/generator.py` + `integrity-check/verify_canaries.sh` | `wazuh-rules/canary_rules.xml` (level 12-13) | T1083, T1486, T1485 | Layer 3 | Alerta crítica en <2s con whodata completo (PID, parent PID, command line); cero archivos reales cifrados | Captura de alerta Wazuh + log del FIM | Lab de P4 (agente Windows/Linux con whodata/auditd configurado) |
| UC-04 | PostgreSQL attack (abuso remoto / lateral) | *(pendiente: log source y carpeta `lateral/` — ver nota en `mitre-mapping.yaml`)* | — | T1021, T1490 (parcial vía vssadmin si aplica) | Layer 1 | — | — | **Pendiente de coordinación con P4** (infraestructura PostgreSQL) y P1 (definición exacta de UC-04) |
| UC-06 | DDoS controlado (hping3 / slowhttptest) | `detection/simulators/uc06_ddos_controlled.py` | `network/ddos_hping3_rate.yml`, `network/slowhttptest_pattern.yml` | T1498, T1499 | Layer 1 | Alerta de tasa anómala dispara dentro de la ventana configurada (10s / 30s); comando rate-limited y con confirmación explícita del operador | Logs de Wazuh + captura del comando ejecutado + captura de tráfico (si P4 expone Zeek/Suricata) | Lab de P4: host víctima + `<VICTIM_LAB_IP>` real (el script ya valida y construye el comando localmente) |
| UC-07 | SELECT masivo benigno (falso positivo legítimo) | *(generador pgAudit no generado en esta entrega — solo regla)* | `database/mass_select_query.yml` | T1213 | Layer 1 | Alerta de severidad media dispara; debe poder cancelarse por un humano sin bloquear el job legítimo | Log de alerta + evidencia de cancelación manual (HITL) | **Pendiente de coordinación con P4** (pgAudit en PostgreSQL del lab) y P1/P2 (flujo de cancelación en SOAR/ML) |
| UC-08 | SQL Injection (sqlmap controlado) | `detection/simulators/uc08_sqli_controlled.py` | `webapp/sql_injection_signatures.yml` | T1190 | Layer 1 | Alerta dispara ante patrones SQLi en request HTTP; sqlmap corre con `--risk=1 --level=1` por defecto, solo tras confirmación explícita | Logs de Wazuh + request capturado + captura del comando confirmado | **Pendiente de coordinación con P4** (app vulnerable del lab; el script ya valida y construye el comando localmente) |

## Notas

- **UC-01, UC-06, UC-08**: los simuladores ya están implementados y probados (`detection/simulators/`, con 14 tests automatizados de sus salvaguardas). Lo que falta es ejecutarlos contra el laboratorio real una vez P4 lo levante — los scripts en sí no requieren ningún cambio para eso, solo el valor real de `<VICTIM_LAB_IP>`.
- **UC-04, UC-07, UC-08** dependen además de infraestructura que P4 aún no ha confirmado (PostgreSQL, app vulnerable). Mientras no se confirme, las reglas Sigma existen pero no se han probado contra un sistema real — solo contra fixtures sintéticos.
- La columna "Resultado esperado" para UC-04 queda vacía porque el caso de uso en sí no está claramente especificado en los documentos que me compartiste — **pendiente de confirmar con P1/P2 la definición exacta de UC-04** antes de poder mapear reglas con precisión.

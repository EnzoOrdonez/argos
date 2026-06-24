# Entregables Finales — P3 (Angeles Castillo)

## ✅ Generados en esta entrega

| Entregable | Ruta | Estado |
|---|---|---|
| README operativo `detection/` | `detection/README.md` | ✅ |
| Requirements `detection/` | `detection/requirements.txt` | ✅ |
| 9 reglas Sigma YAML | `detection/sigma-rules/**/*.yml` | ✅ validadas (sintaxis + MITRE + Atomic pair) |
| Matriz MITRE → reglas | `detection/mitre-mapping.yaml` | ✅ validada |
| Tests de sintaxis Sigma | `detection/tests/test_rule_syntax.py` | ✅ pasa |
| Tests de pareo Atomic | `detection/tests/test_atomic_pairs.py` | ✅ pasa |
| Tests de mapeo MITRE | `detection/tests/test_mitre_mapping.py` | ✅ pasa (1 skip esperado: `argos_contracts` no existe aún) |
| Fixture de evento de ejemplo | `detection/tests/fixtures/vssadmin_delete_shadows_event.json` | ✅ |
| Plantilla de PR upstream | `detection/upstream-prs/001-vssadmin-evasion-variants.md` | ✅ (borrador, no enviado) |
| README operativo `deception/` | `deception/README.md` | ✅ |
| Requirements `deception/` | `deception/requirements.txt` | ✅ |
| Generador de canaries | `deception/canary-generator/generator.py` | ✅ probado end-to-end en sandbox |
| Config de canaries | `deception/canary-generator/config.yaml` | ✅ |
| FIM whodata Windows | `deception/fim-configs/ossec-windows.conf` | ✅ |
| FIM auditd Linux | `deception/fim-configs/ossec-linux.conf` | ✅ |
| Regla Wazuh de canarios (severidad crítica) | `deception/wazuh-rules/canary_rules.xml` | ✅ XML válido |
| Integrity check | `deception/integrity-check/verify_canaries.sh` | ✅ probado (detección + recreación) |
| Tests del generador | `deception/tests/test_generator.py` | ✅ pasa |
| Tests de config FIM | `deception/tests/test_fim_config.py` | ✅ pasa |
| Matriz de validación (Fase 6) | `docs/p3_validation_matrix.md` | ✅ |
| Esta lista de entregables (Fase 8) | `docs/p3_deliverables.md` | ✅ |
| Simulador UC-01 (LockBit-like, sandbox) | `detection/simulators/uc01_lockbit_like.py` | ✅ probado end-to-end (run + cleanup) |
| Simulador UC-06 (DDoS controlado, hping3/slowhttptest) | `detection/simulators/uc06_ddos_controlled.py` | ✅ probado (solo construye/muestra comando por defecto) |
| Simulador UC-08 (SQLi controlado, sqlmap) | `detection/simulators/uc08_sqli_controlled.py` | ✅ probado (solo construye/muestra comando por defecto) |
| README de simuladores | `detection/simulators/README.md` | ✅ |
| Tests de salvaguardas de simuladores | `detection/tests/test_simulators.py` | ✅ pasa (14 tests) |

**Total: 100 tests automatizados pasando, 1 skip intencional.**

## ⏳ Pendiente — siguiente entrega (no generado todavía)

| Entregable | Por qué no se generó | Acción |
|---|---|---|
| Generador pgAudit para UC-07 | No solicitado en esta iteración | Generar si lo necesitas |
| `detection/wazuh-rules/local_rules.xml` (generado) | Requiere correr `sigma-cli convert` con `sigma-cli` instalado — herramienta externa, no se ejecutó en este entorno | Correr `sigma-cli convert -t wazuh -o detection/wazuh-rules/local_rules.xml detection/sigma-rules/` con tu entorno local |
| Texto de exposición (Fase 9) | Ver `docs/p3_exposicion.md` | ✅ generado por separado |

## ⚠️ Pendiente de coordinación con el equipo (no es responsabilidad de P3)

- Agregar `"detection/tests"` a `testpaths` en `pyproject.toml` — **pendiente de confirmar con el equipo** (archivo compartido).
- Confirmar `argos_contracts.MITRE_WHITELIST` (P1) para activar el test que hoy se salta.
- Confirmar rango de IDs de regla Wazuh (100100-100102 son placeholders) — **pendiente de confirmar con P1/P4** para evitar colisiones con otras capas.
- Confirmar fórmula `rule.level` → `severity_score` para el Decision Engine — **pendiente de confirmar con P1**.
- Infraestructura del lab (hosts Windows/Linux, PostgreSQL, app vulnerable, `<WAZUH_MANAGER>` real) — **pendiente de P4**.
- Definición exacta de UC-04 — **pendiente de confirmar con P1/P2**.

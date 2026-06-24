# Upstream PR #1 — vssadmin shadow copy deletion (variantes)

| Campo | Valor |
|---|---|
| Estado | 📝 Borrador — no enviado todavía |
| Regla local | `detection/sigma-rules/ransomware/vssadmin_delete_shadows.yml` |
| Repo destino | https://github.com/SigmaHQ/sigma |
| Técnica MITRE | T1490 |

## Resumen

Plantilla para documentar el PR antes de enviarlo a SigmaHQ/sigma. Llenar esta
tabla por cada PR (copiar este archivo como `002-...md`, `003-...md`, etc.)

## Checklist antes de enviar el PR

- [ ] La regla pasa `sigma-cli check` sin errores.
- [ ] No depende de placeholders del lab (`<VICTIM_LAB_IP>`, etc.) — las reglas
      upstream deben ser genéricas, sin referencias a infraestructura ARGOS.
- [ ] Sigue la convención de naming de SigmaHQ (revisar guía de contribución).
- [ ] Incluye `falsepositives` realistas (no solo "Unknown").
- [ ] Pareada con al menos un test de Atomic Red Team público.

## Pendiente

Pendiente de decidir en equipo cuáles 2-4 reglas se enviarán como upstream PRs
(bonus, no imprescindible para la entrega). Sugerencia: priorizar las reglas
de `ransomware/` y `defense-evasion/` porque son las más genéricas y con menor
dependencia de la infraestructura específica del lab.

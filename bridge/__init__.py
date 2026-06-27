"""Bridge de normalización ARGOS (ADR-0014 / ADR-0015 §2.2, dueño P2/P4).

Convierte alertas reales en `NormalizedAlert` y las publica en el stream Redis
`events:normalized` (campo `payload`), igual que `scripts/demo_injector.py` pero con
datos reales en vez de sintéticos. Dos caminos:

- Camino A (`wazuh_bridge`): tailea el `alerts.json` del Wazuh manager (L1 Sigma, L3 canary).
- Camino B (`ml_publisher`): publica el score ML de Layer 2.

No toca `soar/` ni `argos_contracts/`: solo los importa. El SOAR consume idéntico.
"""

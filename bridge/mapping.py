"""Mapeo PURO: dict de una alerta Wazuh (`alerts.json`) → `NormalizedAlert`.

Sin I/O ni Redis: testeable aislado. ADR-0014 §2.1 manda que la fórmula de
severidad y el mapeo vivan acá (el bridge), NO en `soar/`.

`technique_mitre` (decisión confirmada): del `rule.mitre.id` de la alerta (las reglas
llevan `<mitre><id>`), con el override documentado T1213→T1005 y validación contra
`MITRE_WHITELIST` (el contrato). Se valida contra el whitelist y NO contra el set de
`detection/mitre-mapping.yaml`, porque el yaml está incompleto (no incluye T1485, que
la canary-borrada SÍ emite y SÍ está en el whitelist) — validar contra el yaml la perdería.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from argos_contracts import (
    MITRE_WHITELIST,
    Layer,
    NormalizedAlert,
    Severity,
    WazuhAlert,
)

logger = logging.getLogger(__name__)

# group de la regla Wazuh → capa de detección (ADR-0014 §2.1).
_GROUP_TO_LAYER: dict[str, Layer] = {
    "argos_layer1": Layer.LAYER_1,  # Sigma (conversión Sigma→Wazuh: dependencia P3)
    "argos_layer3": Layer.LAYER_3,  # canary (deception/wazuh-rules/canary_rules.xml)
}

# Override documentado en detection/mitre-mapping.yaml:47-60: T1213 no está en
# MITRE_WHITELIST v1.1.0; se mapea a la técnica de Collection más cercana que sí está.
_TECHNIQUE_OVERRIDES: dict[str, str] = {"T1213": "T1005"}


def source_layer_from_groups(groups: list[str]) -> Layer | None:
    """Primera capa argos encontrada en los groups, o None (alerta ajena al proyecto)."""
    for group in groups:
        layer = _GROUP_TO_LAYER.get(group.strip())
        if layer is not None:
            return layer
    return None


def severity_score_from_level(level: int, layer: Layer) -> float:
    """Wazuh rule.level (0-15) → [0.0, 1.0]. Canary L3 con level≥12 → ≥0.95 (zero-FP)."""
    base = round(max(0, min(level, 15)) / 15, 2)
    if layer == Layer.LAYER_3 and level >= 12:
        return max(base, 0.95)
    return base


def severity_label_from_score(score: float) -> Severity:
    """Mismas bandas que ml.soar_adapter.severity_from_ml_score (replicadas para no
    importar ml/ en el camino liviano Wazuh)."""
    if score >= 0.90:
        return Severity.CRITICAL
    if score >= 0.74:
        return Severity.HIGH
    if score >= 0.40:
        return Severity.MEDIUM
    return Severity.LOW


def technique_from_mitre_ids(mitre_ids: list[str]) -> str | None:
    """Primer `rule.mitre.id` → override → validación whitelist. None si no califica."""
    if not mitre_ids:
        return None
    technique = _TECHNIQUE_OVERRIDES.get(mitre_ids[0].strip(), mitre_ids[0].strip())
    if technique in MITRE_WHITELIST:
        return technique
    logger.warning("técnica %s fuera de MITRE_WHITELIST; technique_mitre=None", technique)
    return None


def _parse_timestamp(raw: str) -> datetime:
    """Parsea el timestamp de Wazuh (ISO, offset 'Z' o '+0000') a datetime tz-aware UTC."""
    text = (raw or "").strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Offset sin ':' que fromisoformat (<algunos casos) no toma: insertarlo.
    if len(text) >= 5 and text[-5] in "+-" and ":" not in text[-5:]:
        try:
            dt = datetime.fromisoformat(f"{text[:-2]}:{text[-2:]}")
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise ValueError(f"timestamp Wazuh no parseable: {raw!r}")


def _file_info(syscheck: dict[str, Any]) -> dict[str, Any] | None:
    keys = ("path", "event", "mode", "sha256_after", "uname_after")
    info = {k: syscheck[k] for k in keys if k in syscheck}
    return info or None


def _process_info(audit: dict[str, Any]) -> dict[str, Any] | None:
    proc = audit.get("process") or {}
    user = audit.get("effective_user") or {}
    info: dict[str, Any] = {}
    for src, dst in (("id", "process_id"), ("ppid", "parent_process_id"),
                     ("name", "process_name"), ("command_line", "command_line")):
        if src in proc:
            info[dst] = proc[src]
    if "name" in user:
        info["user"] = user["name"]
    return info or None


def _wazuh_alert(raw: dict[str, Any], rule: dict[str, Any], agent: dict[str, Any],
                 level: int, timestamp: datetime) -> WazuhAlert | None:
    """Reconstruye el WazuhAlert del contrato para la traza forense. Opcional: si no
    se puede armar, el NormalizedAlert igual se emite con raw_alert=None."""
    try:
        return WazuhAlert(
            alert_id=str(raw.get("id") or rule.get("id") or "unknown"),
            rule_id=int(rule.get("id", 0)),
            rule_description=str(rule.get("description") or ""),
            rule_level=max(0, min(level, 15)),
            timestamp=timestamp,
            agent_id=str(agent.get("id") or "unknown"),
            agent_name=str(agent.get("name") or agent.get("id") or "unknown"),
            agent_ip=agent.get("ip"),
            full_log=raw.get("full_log"),
            decoder_name=(raw.get("decoder") or {}).get("name"),
            location=raw.get("location"),
            mitre_technique_ids=list((rule.get("mitre") or {}).get("id") or []),
            raw_data=raw,
        )
    except (ValueError, TypeError) as exc:
        logger.debug("no se pudo construir WazuhAlert forense: %s", exc)
        return None


def normalize(raw: dict[str, Any]) -> NormalizedAlert | None:
    """Alerta Wazuh (dict de `alerts.json`) → `NormalizedAlert`, o None si no es alerta
    del proyecto (sin group argos) o no se puede parsear (fail-soft)."""
    try:
        rule = raw.get("rule") or {}
        layer = source_layer_from_groups(rule.get("groups") or [])
        if layer is None:
            return None  # alerta ajena al proyecto: se descarta

        level = int(rule.get("level", 0))
        agent = raw.get("agent") or {}
        score = severity_score_from_level(level, layer)
        timestamp = _parse_timestamp(raw.get("timestamp", ""))
        mitre_ids = list((rule.get("mitre") or {}).get("id") or [])

        return NormalizedAlert(
            alert_id=str(raw.get("id") or f"wazuh-{rule.get('id')}-{timestamp.timestamp():.0f}"),
            source_layer=layer,
            timestamp=timestamp,
            host_id=str(agent.get("name") or agent.get("id") or "unknown"),
            host_ip=agent.get("ip"),
            severity_score=score,
            severity_label=severity_label_from_score(score),
            technique_mitre=technique_from_mitre_ids(mitre_ids),
            triggering_rule=rule.get("description"),
            process_info=_process_info((raw.get("data") or {}).get("audit") or {}),
            file_info=_file_info(raw.get("syscheck") or {}),
            raw_alert=_wazuh_alert(raw, rule, agent, level, timestamp),
        )
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("alerta Wazuh no parseable, se descarta: %s", exc)
        return None

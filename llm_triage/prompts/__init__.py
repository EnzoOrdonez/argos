"""Render de los prompts de triage (jinja2). Texto plano: autoescape OFF."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from argos_contracts.triage import AlertContext

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=False,  # noqa: S701 — prompts de texto plano, no HTML; autoescape los rompería
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_system() -> str:
    return _ENV.get_template("system_triage.j2").render()


def render_user(context: AlertContext, whitelist: list[str]) -> str:
    telemetry = json.dumps(context.recent_telemetry, ensure_ascii=False)[:4000]
    return _ENV.get_template("user_triage.j2").render(
        incident_id=context.incident_id,
        host=context.host,
        alert_summary=context.alert_summary,
        recent_telemetry_json=telemetry,
        whitelist=whitelist,
    )

"""View-model puro del Approval Console. Sin Streamlit ni Redis: todo acá es
testeable de forma aislada.

Disciplina (``ui/README.md`` §Contracts): se branchea por **enum**, nunca por
string literal. Cada mapa de color/emoji cubre TODOS los miembros del enum y un
test lo verifica, así un valor nuevo del contrato falla en test, no en el demo.

La consola NO decide la política (eso es de ``soar/approval_api/handlers.py`` y el
scheduler, ADR-0006). Acá solo se leen campos del Incident y se muestran; el
``policy_applied`` se toma verbatim de ``final_decision``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from argos_contracts.enums import (
    ApproverStatus,
    IncidentState,
    NotificationChannelType,
    Severity,
    Tier,
)
from argos_contracts.incident import ConsolidationWindow, Incident

# --- Paletas (ui/README.md:101): T0/T1 rojo, T2 ámbar, T3 azul. -------------

TIER_COLOR: dict[Tier, str] = {
    Tier.T0: "#d32f2f",
    Tier.T1: "#d32f2f",
    Tier.T2: "#f9a825",
    Tier.T3: "#1976d2",
}

APPROVER_STATUS_COLOR: dict[ApproverStatus, str] = {
    ApproverStatus.PENDING: "#f9a825",
    ApproverStatus.APPROVED: "#2e7d32",
    ApproverStatus.REJECTED: "#d32f2f",
    ApproverStatus.TIMEOUT: "#757575",
}

APPROVER_STATUS_EMOJI: dict[ApproverStatus, str] = {
    ApproverStatus.PENDING: "🟡",
    ApproverStatus.APPROVED: "🟢",
    ApproverStatus.REJECTED: "🔴",
    ApproverStatus.TIMEOUT: "⚫",
}

STATE_COLOR: dict[IncidentState, str] = {
    IncidentState.RECEIVED: "#1976d2",
    IncidentState.AWAITING_APPROVAL: "#f9a825",
    IncidentState.PENDING_EXECUTION: "#f9a825",
    IncidentState.PENDING_REJECTION: "#f9a825",
    IncidentState.EXECUTING: "#f9a825",
    IncidentState.EXECUTED: "#2e7d32",
    IncidentState.REVERTED: "#757575",
    IncidentState.REJECTED: "#d32f2f",
    IncidentState.TIMEOUT_ESCALATED: "#d32f2f",
}

SEVERITY_COLOR: dict[Severity, str] = {
    Severity.LOW: "#1976d2",
    Severity.MEDIUM: "#f9a825",
    Severity.HIGH: "#ef6c00",
    Severity.CRITICAL: "#d32f2f",
}

CHANNEL_LABEL: dict[NotificationChannelType, str] = {
    NotificationChannelType.TELEGRAM: "Telegram",
    NotificationChannelType.DISCORD: "Discord",
    NotificationChannelType.TWILIO_VOICE: "Twilio (voz)",
    NotificationChannelType.EMAIL: "Email",
}


# --- Accessors (KeyError explícito si falta un miembro → lo atrapa el test). --

def tier_color(tier: Tier) -> str:
    return TIER_COLOR[tier]


def state_color(state: IncidentState) -> str:
    return STATE_COLOR[state]


def severity_color(severity: Severity) -> str:
    return SEVERITY_COLOR[severity]


def channel_label(channel: NotificationChannelType) -> str:
    return CHANNEL_LABEL[channel]


# --- Ventana de consolidación (60s, ADR-0006). ------------------------------

def consolidation_remaining(
    window: ConsolidationWindow | None, now: datetime | None = None
) -> float | None:
    """Segundos restantes de la ventana, o None si no hay ventana. Nunca negativo."""
    if window is None:
        return None
    current = now if now is not None else datetime.now(timezone.utc)
    deadline = window.started_at.timestamp() + window.duration_seconds
    return max(0.0, deadline - current.timestamp())


def consolidation_elapsed_fraction(
    window: ConsolidationWindow | None, now: datetime | None = None
) -> float:
    """Fracción [0,1] transcurrida de la ventana (para una progress bar)."""
    if window is None or window.duration_seconds <= 0:
        return 0.0
    remaining = consolidation_remaining(window, now) or 0.0
    return max(0.0, min(1.0, 1.0 - remaining / window.duration_seconds))


def format_mmss(seconds: float) -> str:
    """Segundos → 'M:SS' (p.ej. 42.0 → '0:42')."""
    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"


# --- Matriz de decisión. ----------------------------------------------------

@dataclass(frozen=True)
class ApproverRow:
    email: str
    role: str
    status: ApproverStatus
    status_emoji: str
    status_color: str
    latency_label: str
    channel_label: str
    responded_label: str


def approver_rows(incident: Incident) -> list[ApproverRow]:
    rows: list[ApproverRow] = []
    for approver in incident.approvers:
        latency = (
            f"{approver.latency_seconds:.0f}s"
            if approver.latency_seconds is not None
            else "—"
        )
        responded = (
            approver.responded_at.strftime("%H:%M:%S")
            if approver.responded_at is not None
            else "—"
        )
        rows.append(
            ApproverRow(
                email=approver.email,
                role=approver.role,
                status=approver.status,
                status_emoji=APPROVER_STATUS_EMOJI[approver.status],
                status_color=APPROVER_STATUS_COLOR[approver.status],
                latency_label=latency,
                channel_label=CHANNEL_LABEL[approver.channel],
                responded_label=responded,
            )
        )
    return rows


@dataclass(frozen=True)
class VoteCounts:
    approved: int
    rejected: int
    pending: int
    timeout: int

    @property
    def total(self) -> int:
        return self.approved + self.rejected + self.pending + self.timeout


def vote_counts(incident: Incident) -> VoteCounts:
    counts = Counter(a.status for a in incident.approvers)
    return VoteCounts(
        approved=counts[ApproverStatus.APPROVED],
        rejected=counts[ApproverStatus.REJECTED],
        pending=counts[ApproverStatus.PENDING],
        timeout=counts[ApproverStatus.TIMEOUT],
    )


def summary_line(incident: Incident) -> str:
    """Línea resumen estilo 'N approve · N reject · N timeout · <policy> applied'.

    La política sale verbatim de ``final_decision.policy_applied`` (ui/README:157).
    """
    counts = vote_counts(incident)
    parts = [f"{counts.approved} approve", f"{counts.rejected} reject"]
    if counts.timeout:
        parts.append(f"{counts.timeout} timeout")
    if counts.pending:
        parts.append(f"{counts.pending} pending")
    if incident.final_decision is not None:
        parts.append(f"{incident.final_decision.policy_applied} applied")
    return " · ".join(parts)


def is_settled(incident: Incident) -> bool:
    """True si el incidente ya tiene decisión final (read-only helper de display)."""
    return incident.final_decision is not None

"""Reusable Pydantic v2 field validators shared across argos_contracts models.

Single source of truth so that the timezone-aware UTC convention
(per CONTRACTS_SPECIFICATION.md §Conventions) is enforced identically
across every datetime field that crosses a team boundary.
"""

from datetime import datetime


def ensure_tz_aware(v: datetime | None) -> datetime | None:
    """Reject naive datetimes; allow ``None`` for optional fields.

    Forensic timeline correctness depends on every cross-host timestamp
    being unambiguously UTC. Two events from different hosts must be
    directly comparable; naive datetimes silently break that invariant.

    Used as a reusable Pydantic v2 field validator via the pattern::

        _validate_dts = field_validator("created_at", "updated_at")(ensure_tz_aware)

    Parameters
    ----------
    v:
        The datetime value supplied to the model. ``None`` is accepted
        for fields declared as ``datetime | None``.

    Returns
    -------
    datetime | None
        The same value, unchanged, when valid.

    Raises
    ------
    ValueError
        If ``v`` is a naive ``datetime`` (``v.tzinfo is None``).
    """
    if v is not None and v.tzinfo is None:
        raise ValueError("must be timezone-aware (UTC)")
    return v

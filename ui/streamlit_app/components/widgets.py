"""Pequeños helpers de presentación compartidos por los componentes."""

from __future__ import annotations


def badge_html(text: str, color: str, *, text_color: str = "#ffffff") -> str:
    """Devuelve un <span> con fondo de color (chip) para componer con st.markdown."""
    return (
        f"<span style='background:{color};color:{text_color};"
        f"padding:2px 10px;border-radius:6px;font-weight:600;font-size:0.85rem'>"
        f"{text}</span>"
    )

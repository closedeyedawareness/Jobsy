"""
Jobsy UI Theme

People Harmonics-inspired visual system.
This module centralises colour, typography and CSS injection for the Streamlit UI.
"""

from __future__ import annotations

from pathlib import Path
import streamlit as st

COLORS = {
    # Core surfaces
    "bg": "#160A2B",
    "surface": "#22103F",
    "surface2": "#2C1652",
    "surface3": "#351B63",

    # Text
    "ink": "#FFFFFF",
    "text": "#FFFFFF",
    "muted": "#C9B8E8",
    "subtle": "#9E87C9",
    "line": "#4D2F75",
    "border": "#4D2F75",

    # Brand accents
    "primary": "#6F3CFF",
    "secondary": "#34B5FF",
    "accent": "#FF73D0",
    "gold": "#CFA46A",

    # Backwards-compatible aliases used by app.py
    "teal": "#34B5FF",
    "teal2": "#70D6FF",
    "blue": "#6F3CFF",
    "violet": "#A77BFF",
    "amber": "#F4B942",
    "clay": "#FF5A7A",

    # Semantic
    "success": "#00C897",
    "warning": "#F4B942",
    "danger": "#FF5A7A",
}

FONT = {
    "serif": "'Fraunces', Georgia, serif",
    "sans": "'IBM Plex Sans', system-ui, sans-serif",
    "mono": "'IBM Plex Mono', 'Courier New', monospace",
}

RADIUS = {
    "sm": 8,
    "md": 12,
    "lg": 18,
    "xl": 24,
}

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 16,
    "lg": 24,
    "xl": 32,
}


def load_fonts() -> None:
    """Load Jobsy web fonts."""
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&'
        'family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )


def inject_theme() -> None:
    """Inject the Jobsy CSS design system into Streamlit."""
    css_path = Path(__file__).parent / "assets" / "jobsy.css"
    if css_path.exists():
        st.markdown(
            f"<style>{css_path.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


def apply_theme() -> None:
    """Load fonts and inject CSS."""
    load_fonts()
    inject_theme()

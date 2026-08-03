"""
Jobsy UI Theme

People Harmonics-inspired visual system.
This module centralises colour, typography and CSS injection for the Streamlit UI.
"""

from __future__ import annotations

from pathlib import Path
import streamlit as st

# The People Harmonics palette, verbatim from PH-www/styles.css, which in turn
# takes it from hrs.peopleharmonics.com. Jobsy had its own near-miss of this
# palette -- close enough to look like a mistake rather than a decision -- so
# these are now the same hex values the front door and the engine use.
#
# Every key that existed before is kept, including the aliases, because they are
# read ~500 times across app.py and the services. They are REPOINTED, not
# renamed: nothing downstream has to change for the charts to follow the brand.
COLORS = {
    # Core surfaces — PH ground/panel ramp
    "bg": "#150226",          # --ground
    "bg2": "#0b0016",         # --ground2
    "surface": "#1d0b38",     # --panel
    "surface2": "#271052",    # --panel2
    "surface3": "#2C1652",

    # Text — PH ink ramp
    "ink": "#EDE6FF",
    "text": "#EDE6FF",
    "muted": "#B9A6DD",
    "subtle": "#8A78B0",      # --faint
    "line": "#3a2064",
    "line2": "#4d2c80",
    "border": "#3a2064",

    # Brand accents
    "primary": "#8850EF",     # --ac
    "secondary": "#67E8F9",
    "accent": "#F565BF",      # --script-pink
    "gold": "#E6B25E",

    # The four pillars — the same tokens the HRS engine scores on
    "iai": "#A87CFF",         # Inner Alignment Index
    "rri": "#F472B6",         # Relational Resonance Index
    "lhi": "#67E8F9",         # Leadership Harmonic Impact
    "ohb": "#6EE7B7",         # Organizational Harmonics Baseline

    # Aliases kept for app.py and the report services, repointed onto the
    # pillar palette so every existing chart inherits the brand for free.
    "teal": "#67E8F9",        # -> lhi
    "teal2": "#9BF0FA",
    "blue": "#8850EF",        # -> ac
    "violet": "#A87CFF",      # -> iai
    "amber": "#E6B25E",       # -> gold
    "clay": "#F472B6",        # -> rri

    # Semantic
    "success": "#6EE7B7",     # -> ohb
    "warning": "#E6B25E",
    "danger": "#FF5A7A",

    # ── ON LIGHT SURFACES ────────────────────────────────────────────────
    # Some components render on a near-white card (#F8FAFB and friends) inside
    # an otherwise dark app. Everything above is tuned for a dark ground and is
    # illegible there -- "ink" on a white card is white on white.
    #
    # These come from People Harmonics' own LIGHT palette, corporate.css in the
    # HRS suite, so a light card is still PH rather than an invention.
    "on_light_ink": "#0B1729",     # headings/body on white  (--ink)
    "on_light_body": "#3D4C60",    # secondary copy          (--body)
    "on_light_muted": "#6B7A8F",   # captions, meta          (--muted)
    "on_light_line": "#E3E8EF",    # hairlines               (--line)
    "on_light_accent": "#1B4DD8",  # eyebrows, links         (--blue)
    "on_light_tint": "#F4F7FE",    # accent wash             (--blue-tint)

    # A fill dark enough to carry WHITE text. --lhi (#67E8F9) is a highlight,
    # not a fill: white on it fails contrast badly. Use this instead anywhere
    # the pattern is background=<accent>, color=#fff.
    "fill_accent": "#1B4DD8",
    "fill_accent_deep": "#0B2A5B",
}

FONT = {
    # PH leads on Quicksand for display and plain system sans for body text;
    # Jobsy was on Fraunces, a serif, which was the loudest single thing making
    # the two products look unrelated.
    "display": "'Quicksand', system-ui, sans-serif",
    "script": "'Sacramento', cursive",
    "sans": "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    "mono": "'IBM Plex Mono', 'SF Mono', ui-monospace, Menlo, Consolas, monospace",
}
# Deprecated: "serif" is what the display face used to be called here. Kept as an
# alias so nothing breaks, but it now resolves to Quicksand, which is not a serif.
FONT["serif"] = FONT["display"]

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
    """Load the People Harmonics web fonts.

    Quicksand (display) and Sacramento (script accent) replace Fraunces; IBM Plex
    Mono stays, since PH uses it too. IBM Plex Sans is dropped because PH sets
    body copy in the system stack, which also means one less font to fetch.
    """
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@500;600;700&'
        'family=Sacramento&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">',
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

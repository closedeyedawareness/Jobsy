"""
Reusable Jobsy UI components.

These helpers keep HTML generation out of app.py and centralise styling.
"""

from __future__ import annotations

import streamlit as st

from ui.theme import COLORS as C, FONT


def chip(text: str, bg: str | None = None, fg: str | None = None, size: str = "11px") -> str:
    bg = bg or f'{C["primary"]}22'
    fg = fg or C["ink"]
    return (
        f'<span style="display:inline-block;font-family:{FONT["mono"]};font-size:{size};'
        f'font-weight:500;background:{bg};color:{fg};border-radius:999px;'
        f'padding:4px 10px;margin:2px 4px 2px 0;border:1px solid rgba(255,255,255,.10)">'
        f'{text}</span>'
    )


def stat_card(value, label: str, color: str | None = None) -> str:
    color = color or C["ink"]
    return (
        f'<div class="jobsy-metric-card" style="flex:1;padding:16px 12px;text-align:center">'
        f'<div style="font-family:{FONT["mono"]};font-weight:700;font-size:28px;'
        f'line-height:1;color:{color}">{value}</div>'
        f'<div style="font-family:{FONT["mono"]};font-size:9.5px;letter-spacing:.12em;'
        f'text-transform:uppercase;color:{C["muted"]};margin-top:6px">{label}</div>'
        f'</div>'
    )


def section_header(title: str, subtitle: str = "", pill: str | None = None) -> None:
    pill_html = (
        f'<span class="jobsy-pill" style="margin-left:10px">{pill}</span>'
        if pill else ""
    )
    st.markdown(
        f'<div class="jobsy-hero" style="margin-bottom:20px">'
        f'<div style="font-family:{FONT["serif"]};font-size:42px;font-weight:700;'
        f'letter-spacing:-.03em;line-height:1.05" class="jobsy-gradient-text">{title}</div>'
        f'{pill_html}'
        f'<p style="color:{C["muted"]};font-size:15.5px;margin:12px 0 0;'
        f'max-width:62ch;line-height:1.55">{subtitle}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def info_card(content: str, border_color: str | None = None) -> str:
    border_color = border_color or C["line"]
    return (
        f'<div class="jobsy-card" style="border-left:4px solid {border_color};'
        f'padding:18px;margin-bottom:12px">{content}</div>'
    )

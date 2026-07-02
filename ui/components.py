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


# ── Commit 4.1: status & diagnostics components ───────────────────────────

def status_badge(state: str, label: str | None = None) -> str:
    """
    Small pill indicating system state.
    state: "ok" | "warn" | "error" | "off"
    """
    palette = {
        "ok":    (C["success"], f'{C["success"]}22', label or "Connected"),
        "warn":  (C["warning"], f'{C["warning"]}22', label or "Degraded"),
        "error": (C["danger"],  f'{C["danger"]}22',  label or "Error"),
        "off":   (C["subtle"],  f'{C["subtle"]}22',  label or "Inactive"),
    }
    fg, bg, text = palette.get(state, palette["off"])
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'font-family:{FONT["mono"]};font-size:10px;font-weight:600;'
        f'letter-spacing:.08em;text-transform:uppercase;'
        f'background:{bg};color:{fg};border-radius:999px;padding:4px 11px;'
        f'border:1px solid {fg}44">'
        f'<span style="width:7px;height:7px;border-radius:50%;background:{fg};'
        f'box-shadow:0 0 6px {fg}"></span>{text}</span>'
    )


def status_card(title: str, state: str, detail: str = "",
                badge_label: str | None = None) -> str:
    """
    Card showing a system's status with badge and optional detail line.
    state: "ok" | "warn" | "error" | "off"
    """
    border = {
        "ok": C["success"], "warn": C["warning"],
        "error": C["danger"], "off": C["line"],
    }.get(state, C["line"])
    detail_html = (
        f'<div style="font-family:{FONT["sans"]};font-size:12.5px;'
        f'color:{C["muted"]};margin-top:8px;line-height:1.5">{detail}</div>'
    ) if detail else ""
    return (
        f'<div class="jobsy-card" style="border-left:4px solid {border};'
        f'padding:14px 16px;margin-bottom:10px">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;gap:10px">'
        f'<div style="font-family:{FONT["sans"]};font-size:13.5px;font-weight:600;'
        f'color:{C["ink"]}">{title}</div>'
        f'{status_badge(state, badge_label)}'
        f'</div>{detail_html}</div>'
    )


def info_tile(label: str, value, sub: str = "", color: str | None = None) -> str:
    """
    Compact key/value tile for diagnostics and dashboards.
    """
    color = color or C["secondary"]
    sub_html = (
        f'<div style="font-family:{FONT["mono"]};font-size:9px;'
        f'color:{C["subtle"]};margin-top:3px">{sub}</div>'
    ) if sub else ""
    return (
        f'<div class="jobsy-card" style="flex:1;min-width:110px;'
        f'padding:12px 14px;text-align:left">'
        f'<div style="font-family:{FONT["mono"]};font-size:9.5px;'
        f'letter-spacing:.12em;text-transform:uppercase;color:{C["muted"]}">{label}</div>'
        f'<div style="font-family:{FONT["mono"]};font-size:17px;font-weight:700;'
        f'color:{color};margin-top:5px;word-break:break-word">{value}</div>'
        f'{sub_html}</div>'
    )

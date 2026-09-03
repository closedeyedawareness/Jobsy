"""ui/views/job_family.py — moved verbatim out of ui/app.py on 2026-09-03."""

from __future__ import annotations

from ui.shared import *  # noqa: F401,F403


def _family_frames(catalog):
    """The Job Family sheets, from the library the app has actually loaded.

    This read the workbook directly until 2026-09-03 — so after the cutover the
    Job Family page was drawing its levelling grid and its pay bands from a file
    nothing else in the app reads. Same drift as the Data Quality scorecard, and
    worse here, because these are salary numbers.

    PayMix used to be fetched separately here, because it had no SHEET_MAP
    entry. It has one now, and the pay composition comes through
    services/pay_components_service instead of a frame read by hand.
    """
    frames = getattr(catalog, "frames", None) or {}
    wanted = (("Jobs", "jobs"), ("SalaryBands", "salary"),
              ("JobGrades", "jobgrades"), ("JobProfiles", "profiles"))
    out = {}
    for sheet, key in wanted:
        df = frames.get(key)
        if df is None:
            raise KeyError(f"The loaded library has no {sheet}.")
        out[sheet] = df
    return out


def job_family_page(catalog):
    """Leveling grid + pay range for a job family (function), Mercer/Hay style."""
    import pandas as _pd
    import altair as _alt

    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Job Family</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'A leveling grid and pay range for a job family — every role by level, with grade, '
        f'salary band and what changes as you move up the ladder.</p>',
        unsafe_allow_html=True,
    )
    try:
        fr = _family_frames(catalog)
    except Exception as exc:
        st.warning(f"Job Family needs Jobs, SalaryBands, JobGrades and JobProfiles in the loaded library. ({exc})")
        return

    jobs = fr["Jobs"].copy(); bands = fr["SalaryBands"].copy()
    grades = fr["JobGrades"].copy(); profs = fr["JobProfiles"].copy()
    jobs["Grade"] = _pd.to_numeric(jobs.get("Grade"), errors="coerce")
    for _c in ("Grade", "Min", "P25", "P50", "P75", "Max"):
        if _c in bands: bands[_c] = _pd.to_numeric(bands[_c], errors="coerce")
    grades["Grade"] = _pd.to_numeric(grades.get("Grade"), errors="coerce")

    funcs = sorted(jobs["Function"].dropna().unique())
    if not funcs:
        st.info("No roles found."); return
    fsel = st.selectbox("Job family", funcs,
                        index=funcs.index("Engineering") if "Engineering" in funcs else 0)

    fam = jobs[jobs["Function"] == fsel].dropna(subset=["Grade"]).sort_values("Grade")
    if fam.empty:
        st.info("No roles in this family."); return

    bmap = {(r["Function"], r["Level"]): r for _, r in bands.iterrows()}
    gmap = {r["Grade"]: r for _, r in grades.iterrows()}
    pmap = {r["JobID"]: r for _, r in profs.iterrows()}
    # Pay composition comes from the library through one service, so the rates
    # in this table are the rows in PayElements and PayMix and not literals.
    from services import pay_components_service as _pay
    _repo = catalog.repository

    def _euro0(v):
        try: return _money(float(v))
        except Exception: return "—"
    def _cell(v, n=170):
        s = "" if v is None else str(v)
        if not s or s.lower() == "nan": return "—"
        s = s.replace(";", " · ")
        return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"
    def _skills_for(jid):
        try:
            names = [sk.skill_name for _, sk in catalog.get_role_skills(jid)[:3]]
            return " · ".join(names) if names else "—"
        except Exception:
            return "—"

    cols = []
    for role in fam.itertuples(index=False):
        jid = getattr(role, "JobID"); lvl = getattr(role, "Level"); fn = getattr(role, "Function")
        b = bmap.get((fn, lvl)); g = gmap.get(getattr(role, "Grade")); p = pmap.get(jid)
        base = b.get("P50") if b is not None else None
        base = None if (base is None or _pd.isna(base)) else float(base)
        comp = _pay.compose(base, fn, lvl, _repo) if base is not None else None

        def _line(key):
            """The cell for one component: amount and the rate behind it."""
            if comp is None:
                return "—"
            c = next((c for c in comp.components if c.key == key), None)
            if c is not None and c.computable:
                return f'{_euro0(c.amount)} ({c.pct:g}%)'
            if c is not None and c.ranged:
                return (f'{_euro0(c.low_amount)} – {_euro0(c.high_amount)} '
                        f'({c.low_pct:g}–{c.high_pct:g}%)')
            c = next((c for c in comp.excluded if c.key == key), None)
            return "not stated" if c is not None else "—"
        cols.append({
            "title": _cell(getattr(role, "StandardTitle"), 60), "level": _cell(lvl, 20),
            "code": _cell(jid, 20), "grade": _cell(getattr(role, "Grade"), 6),
            "band": (f'{_euro0(b.get("Min"))} – {_euro0(b.get("Max"))}' if b is not None else "—"),
            "med": (_euro0(b.get("P50")) if b is not None else "—"),
            "hol": _line("holiday"),
            "m13": _line("thirteenth"),
            "var": _line("variable"),
            "ttc": (_euro0(comp.total_target_cash) if comp is not None else "—"),
            "pens": _line("pension"),
            "ben": _line("benefits"),
            "treward": ((f'{_euro0(comp.total_reward_low)} – {_euro0(comp.total_reward_high)}'
                         if comp.is_range else _euro0(comp.total_target_cash))
                        if comp is not None else "—"),
            "lti": ("—" if comp is None or comp.lti_eligible is None
                    else ("Yes" if comp.lti_eligible else "No")),
            "knowledge": _cell(g.get("Scope") if g is not None else None),
            "problem": _cell(g.get("Complexity") if g is not None else None),
            "account": _cell(g.get("DecisionRights") if g is not None else None),
            "lead": _cell(g.get("Leadership") if g is not None else None, 60),
            "skills": _skills_for(jid),
        })

    def _th(c):
        return (f'<th style="min-width:200px;text-align:left;padding:10px 12px;'
                f'background:{C["fill_accent"]};color:#fff;border:1px solid {C["line"]}">'
                f'<div style="font-family:{FONT_SANS};font-weight:700;font-size:13px">{c["title"]}</div>'
                f'<div style="font-family:{FONT_MONO};font-size:10px;opacity:.85;margin-top:2px">'
                f'{c["level"]} · {c["code"]}</div></th>')
    def _row(label, key, mono=False):
        cells = "".join(
            f'<td style="padding:9px 12px;border:1px solid {C["line"]};vertical-align:top;'
            f'font-size:12px;color:{C["ink"]};{"font-family:"+FONT_MONO+";" if mono else ""}">'
            f'{c[key]}</td>' for c in cols)
        return (f'<tr><td style="padding:9px 12px;border:1px solid {C["line"]};'
                f'background:{C["surface"]};font-family:{FONT_MONO};font-size:11px;'
                f'color:{C["muted"]};white-space:nowrap">{label}</td>{cells}</tr>')

    grid = (
        f'<div style="overflow-x:auto;border-radius:12px;border:1px solid {C["line"]};margin-top:6px">'
        f'<table style="border-collapse:collapse;width:100%">'
        f'<tr><th style="background:{C["surface"]};border:1px solid {C["line"]};min-width:130px"></th>'
        + "".join(_th(c) for c in cols) + "</tr>"
        + _row("Grade", "grade", mono=True) + _row("Salary band", "band", mono=True)
        + _row("Median (P50)", "med", mono=True)
        + _row("+ Holiday allowance", "hol", mono=True)
        + _row("+ 13th month", "m13", mono=True)
        + _row("+ Variable (on-target)", "var", mono=True)
        + _row("= Total target cash", "ttc", mono=True)
        + _row("+ Employer pension", "pens", mono=True)
        + _row("+ Other benefits", "ben", mono=True)
        + _row("= Total reward", "treward", mono=True)
        + _row("LTI eligible", "lti", mono=True)
        + _row("Knowledge / scope", "knowledge")
        + _row("Problem solving", "problem") + _row("Accountability", "account")
        + _row("Leadership", "lead") + _row("Top skills", "skills")
        + "</table></div>"
    )
    st.markdown(grid, unsafe_allow_html=True)
    _sources = ("Every rate above comes from the reference library: holiday allowance and "
                "employer pension from **PayElements**, the 13th month and on-target variable "
                "from **PayMix** for that exact Function × Level. Pension is stated as a range, "
                "so total reward is a range. Components the library does not state as a rate "
                "read *not stated* and are left out of the totals rather than estimated.")
    st.caption(_sources)

    # ── pay range chart ─────────────────────────────────────────────────
    rows, order = [], []
    for role in fam.itertuples(index=False):
        b = bmap.get((getattr(role, "Function"), getattr(role, "Level")))
        if b is None or _pd.isna(b.get("Min")): continue
        label = str(getattr(role, "StandardTitle"))
        order.append(label)
        rows.append({"Role": label, "Level": getattr(role, "Level"),
                     "Min": b.get("Min"), "P25": b.get("P25"), "Median": b.get("P50"),
                     "P75": b.get("P75"), "Max": b.get("Max")})
    if rows:
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:{C["muted"]};margin:20px 0 4px">Pay range by level</div>',
            unsafe_allow_html=True)
        df = _pd.DataFrame(rows)
        tips = ["Role", "Level"] + [_alt.Tooltip(f"{f}:Q", format=",.0f")
                                    for f in ("Min", "P25", "Median", "P75", "Max")]
        base = _alt.Chart(df).encode(x=_alt.X("Role:N", sort=order, axis=_alt.Axis(labelAngle=-20, title=None)))
        rule = base.mark_rule(color="#8850EF", strokeWidth=2, opacity=0.45).encode(
            y=_alt.Y("Min:Q", title=f"Base salary ({_cur()})"), y2="Max:Q")
        def _pt(field, shape, color, size=70):
            return base.mark_point(shape=shape, filled=True, color=color, size=size, opacity=0.9).encode(
                y=f"{field}:Q", tooltip=tips)
        chart = (rule + _pt("P25", "triangle-down", "#67E8F9") + _pt("P75", "triangle-up", "#67E8F9")
                 + _pt("Median", "circle", "#F565BF", 170)).properties(height=340)
        chart = chart.configure_view(strokeOpacity=0).configure_axis(
            labelColor="#B9A6DD", titleColor="#B9A6DD", gridColor="#FFFFFF14", domainColor="#FFFFFF30")
        st.altair_chart(chart, use_container_width=True)
        st.caption("● median (P50)   ▲ P75   ▼ P25   │ min–max band")

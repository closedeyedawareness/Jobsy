"""ui/pages/benefits.py — moved verbatim out of ui/app.py on 2026-09-03."""

from __future__ import annotations

from ui.shared import *  # noqa: F401,F403


def benefits_benchmarking_page(catalog, benefits_svc):
    """Benchmark a benefits package against market percentiles (P25/median/P75/P90),
    computed from the self-built benefits reference library, with rule-based advice
    and a Total Rewards snapshot bridging Pay + Benefits."""
    import io as _io
    import pandas as _pd

    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Benefits Benchmarking</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Benchmark your employee benefits package against market percentiles and the median — '
        f'computed from a self-built reference library, by industry and level — with rule-based '
        f'advice and a report export.</p>',
        unsafe_allow_html=True,
    )
    if benefits_svc is None:
        st.error("benefits_service.py not found in services/")
        return

    repo = catalog.repository
    if not repo.benefits_catalog:
        st.warning("No BenefitsCatalog data found in the reference workbook.")
        return

    ind_id = st.session_state.get("industry_id")
    ind_name = st.session_state.get("industry_name", "General (NL baseline)")
    levels = repo.levels or ["Junior", "Medior", "Senior", "Lead"]
    level = st.selectbox("Level", levels, index=levels.index("Medior") if "Medior" in levels else 0)
    st.caption(f"Industry context: **{ind_name}** (change in the sidebar) · Level: **{level}**")

    # ── input table ──────────────────────────────────────────────────────
    cats = benefits_svc.categories()
    rows = []
    for cat in cats:
        item = benefits_svc.catalog_item(cat)
        rows.append({"Category": cat, "Unit": item.unit if item else "", "Offered": False, "Your value": 0.0})
    df_input = _pd.DataFrame(rows)
    st.markdown(
        f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
        f'text-transform:uppercase;color:{C["muted"]};margin:8px 0 6px">Your benefits package</div>',
        unsafe_allow_html=True)
    edited = st.data_editor(
        df_input, use_container_width=True, hide_index=True, num_rows="fixed",
        column_config={
            "Category":   st.column_config.TextColumn("Category", disabled=True, width="medium"),
            "Unit":       st.column_config.TextColumn("Unit", disabled=True, width="small"),
            "Offered":    st.column_config.CheckboxColumn("Offered?", width="small"),
            "Your value": st.column_config.NumberColumn("Your value", min_value=0.0, step=1.0, width="small"),
        },
        key="benefits_input_editor",
    )

    package = {r["Category"]: r["Your value"] for _, r in edited.iterrows() if r["Offered"]}
    offered = set(package.keys())

    if not package:
        st.info("Tick **Offered** and enter a value for at least one benefit to see the market comparison.")
        return

    comparisons = benefits_svc.compare_package(package, ind_id, level)
    idx = benefits_svc.benefits_richness_index(comparisons)

    # ── headline tiles ───────────────────────────────────────────────────
    below_p25 = sum(1 for c in comparisons if c.status == "Below P25")
    above_p75 = sum(1 for c in comparisons if c.status in ("Above P75", "Above P90"))
    tiles = [("Benefits Richness Index", f"{idx:.0f}/100", C["teal"] if idx >= 50 else C["amber"]),
             ("Categories compared", str(len(comparisons)), C["ink"]),
             ("Below P25", str(below_p25), C["danger"] if below_p25 else C["ink"]),
             ("Above P75", str(above_p75), C["blue"] if above_p75 else C["ink"])]
    trow = "".join(
        f'<div style="flex:1;min-width:130px;background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-radius:12px;padding:14px 16px"><div style="font-family:{FONT_SERIF};font-size:26px;'
        f'font-weight:700;color:{col}">{val}</div><div style="font-family:{FONT_MONO};font-size:10px;'
        f'letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]};margin-top:2px">{lab}</div></div>'
        for lab, val, col in tiles)
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 16px">{trow}</div>',
                unsafe_allow_html=True)
    st.caption("Benefits Richness Index = average percentile rank of your offered benefits vs. the "
               "market distribution for this industry/level (50 = at market median).")

    # ── chart: your value vs P25/median/P75/P90 per category ─────────────
    STATUS_COLOR = {"Below P25": "#E0555F", "Below median": "#D9932B", "At market": "#0E9E7E",
                    "Above P75": "#67E8F9", "Above P90": "#A87CFF"}
    chart_rows = [{"Category": c.category, "Your value": c.actual, "P25": c.band.p25,
                   "Median": c.band.p50, "P75": c.band.p75, "P90": c.band.p90,
                   "Status": c.status, "Unit": c.unit} for c in comparisons]
    cdf = _pd.DataFrame(chart_rows)
    try:
        import altair as _alt
        base = _alt.Chart(cdf).encode(y=_alt.Y("Category:N", title=None))
        rule = base.mark_rule(color="#8850EF", strokeWidth=2, opacity=0.4).encode(
            x=_alt.X("P25:Q", title="Value (category-specific unit)"), x2="P90:Q")
        median_tick = base.mark_tick(color="#F565BF", thickness=3, size=22).encode(x="Median:Q")
        actual_pt = base.mark_point(shape="diamond", filled=True, size=140, opacity=0.95).encode(
            x="Your value:Q",
            color=_alt.Color("Status:N", scale=_alt.Scale(domain=list(STATUS_COLOR), range=list(STATUS_COLOR.values())),
                              legend=_alt.Legend(orient="bottom")),
            tooltip=["Category", "Your value", "P25", "Median", "P75", "P90", "Status"])
        chart = (rule + median_tick + actual_pt).properties(height=max(220, 40 * len(cdf)))
        chart = chart.configure_view(strokeOpacity=0).configure_axis(
            labelColor="#B9A6DD", titleColor="#B9A6DD", gridColor="#FFFFFF14", domainColor="#FFFFFF30"
        ).configure_legend(labelColor="#B9A6DD", titleColor="#B9A6DD")
        st.altair_chart(chart, use_container_width=True)
        st.caption("─ P25–P90 range   | median tick   ◆ your value, colored by status")
    except Exception:
        pass

    # ── table + export ────────────────────────────────────────────────────
    show = cdf[["Category", "Your value", "P25", "Median", "P75", "P90", "Status"]]
    def _row_style(row):
        color = STATUS_COLOR.get(row["Status"], "#8A93A5")
        return [f"color:{color};font-weight:600" if col == "Status" else "" for col in row.index]
    st.dataframe(show.style.apply(_row_style, axis=1), use_container_width=True, hide_index=True)

    _xb = _io.BytesIO(); show.to_excel(_xb, index=False)
    st.download_button("⬇ Download benefits benchmarking (.xlsx)", _xb.getvalue(),
        file_name="jobsy_benefits_benchmarking.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ── advice ─────────────────────────────────────────────────────────────
    advice = benefits_svc.generate_advice(comparisons, offered)
    if advice:
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:{C["muted"]};margin:20px 0 6px">Advice</div>',
            unsafe_allow_html=True)
        SEV_COLOR = {"high": C["danger"], "medium": C["amber"], "low": C["muted"]}
        for a in advice[:8]:
            col = SEV_COLOR.get(a["severity"], C["muted"])
            st.markdown(
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-left:4px solid {col};'
                f'border-radius:10px;padding:10px 14px;margin-bottom:8px">'
                f'<div style="font-family:{FONT_SANS};font-weight:700;font-size:13px;color:{C["ink"]}">{a["title"]}</div>'
                f'<div style="font-family:{FONT_SANS};font-size:12.5px;color:{C["muted"]};margin-top:3px">{a["detail"]}</div>'
                f'</div>', unsafe_allow_html=True)

    # ── Total Rewards snapshot (Pay + Benefits, first step toward the unified center) ──
    st.markdown(
        f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
        f'text-transform:uppercase;color:{C["muted"]};margin:20px 0 6px">Total Rewards snapshot</div>',
        unsafe_allow_html=True)
    st.caption("Bring Pay + Benefits together: pick a function and your actual base salary to see a combined position.")
    funcs = sorted(repo.jobs_by_function.keys())
    if funcs:
        colA, colB = st.columns(2)
        with colA:
            fsel = st.selectbox("Function (for pay comparison)", funcs,
                                index=funcs.index("Engineering") if "Engineering" in funcs else 0,
                                key="tr_function")
        with colB:
            actual_pay = st.number_input("Your actual base salary (€, optional)", min_value=0.0, step=1000.0,
                                         value=0.0, key="tr_actual_pay")
        pay_compa = None
        if actual_pay:
            band = catalog.industry_adjusted_band(fsel, level, ind_id)
            if band and band.p50:
                pay_compa = round(actual_pay / band.p50, 2)
        snap = benefits_svc.total_rewards_snapshot(idx, pay_compa)
        tr_tiles = [
            ("Pay position", f"{snap['pay_score']:.0f}/100" if snap["pay_score"] is not None else "—", C["blue"]),
            ("Benefits position", f"{snap['benefits_score']:.0f}/100", C["violet"]),
            ("Total Rewards score", f"{snap['total_rewards_score']:.0f}/100",
             C["teal"] if snap["total_rewards_score"] >= 50 else C["amber"]),
        ]
        trow2 = "".join(
            f'<div style="flex:1;min-width:150px;background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-radius:12px;padding:14px 16px"><div style="font-family:{FONT_SERIF};font-size:24px;'
            f'font-weight:700;color:{col}">{val}</div><div style="font-family:{FONT_MONO};font-size:10px;'
            f'letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]};margin-top:2px">{lab}</div></div>'
            for lab, val, col in tr_tiles)
        st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap">{trow2}</div>', unsafe_allow_html=True)
        st.caption("Pay position = compa-ratio (actual ÷ market P50) rescaled to 0–100 (100 = at market). "
                   "Benefits position = Benefits Richness Index. Total Rewards score is their average — "
                   "an early step toward bringing Pay and Benefits Benchmarking together in one center.")

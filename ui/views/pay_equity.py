"""ui/views/pay_equity.py — moved verbatim out of ui/app.py on 2026-09-03."""

from __future__ import annotations

from ui.shared import *  # noqa: F401,F403


def _is_dutch_client() -> bool:
    """Whether the Dutch collective-agreement crosswalk may be shown at all.

    ISF and CATS are Metalektro institutions -- Dutch ones -- which is exactly
    why cao_crosswalk_service encodes them as code rather than data. Rendering
    them for a Polish client positions their grades onto Dutch salarisgroepen
    beside euro monthly scales, implying a legal classification that does not
    apply to them. Germany's ERA and France's conventions collectives are
    different institutions, not different numbers, so each becomes its own
    module rather than a translated label.

    Both crosswalk render sites call this, so the rule lives in one place and
    the two cannot drift apart.

    The name is now narrower than the question. What this actually asks is
    "do we hold a crosswalk we can honestly render for this market", and that
    stopped being the same as "is the client Dutch" the moment a second country
    pack existed: Belgium has PC 200 and Germany has ERA, and neither is Dutch.
    So the body delegates to `country_packs.has_crosswalk()`, which answers the
    real question from data, while the name stays put because two existing
    guard tests assert on it and renaming would edit the guard alongside the
    thing it guards. For NL the answer is unchanged.
    """
    try:
        from services import country_packs
        return country_packs.has_crosswalk(system="ISF")
    except Exception:
        try:
            from services import country_service
            return country_service.active_country() == "NL"
        except Exception:
            return True     # no session to ask: the library is Dutch


def _render_leveled_gap(df, *, function_col, level_col, gender_col, salary_col, fte_col=None, tenure_col=None, age_col=None, salary_already_fte=False, catalog=None):
    """
    Option A — structural gender pay gap straight from a client's leveled grid
    (Function + Level + Gender + Salary), with no job-title matching or bands.
    Backed by services.pay_equity_service.analyze_gender_pay_gap.
    """
    import pandas as pd
    try:
        from services.pay_equity_service import (
            analyze_gender_pay_gap, DIRECTIVE_THRESHOLD_PCT, flip_gap_sign, flip_gap_ci)
    except ImportError:
        from jobsy.services.pay_equity_service import (
            analyze_gender_pay_gap, DIRECTIVE_THRESHOLD_PCT, flip_gap_sign, flip_gap_ci)

    det = [("Function", function_col), ("Level", level_col), ("Gender", gender_col),
           ("Salary", salary_col), ("FTE", fte_col), ("Tenure", tenure_col)]
    st.caption("Leveled-grid mode · " + " · ".join(f"{lab}: **{c}**" for lab, c in det if c))
    if not salary_col:
        st.error("No salary column found — include an annual salary column."); return
    if not gender_col:
        st.info("➕ Add a **Gender** column (M / F — Dutch M / V is read natively) to compute the gender pay gap."); return

    r = analyze_gender_pay_gap(df, function_col=function_col, level_col=level_col,
                               gender_col=gender_col, salary_col=salary_col, fte_col=fte_col,
                               tenure_col=tenure_col, age_col=age_col, salary_already_fte=salary_already_fte)
    if not r.has_gap:
        st.info(f"Need both men and women with pay to compute a gap (M n={r.n_m}, F n={r.n_f})."); return

    # Display in the wetsvoorstel's own sign convention -- (vrouw-man)/man, positive
    # = women paid more -- rather than PayGapResult's internal "men paid more" one,
    # so this screen always matches the downloaded report (PayEquityExportService
    # applies the same flip).
    mean_gap = flip_gap_sign(r.mean_gap_pct)
    median_gap = flip_gap_sign(r.median_gap_pct)
    adjusted_gap = flip_gap_sign(r.adjusted_gap_pct)
    adjusted_ci = flip_gap_ci(r.adjusted_ci)

    def _col(v):
        return C["danger"] if (v is not None and abs(v) >= DIRECTIVE_THRESHOLD_PCT) else C["teal"]

    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:14px 0 6px">'
                f'Gender pay gap · Function × Level</div>', unsafe_allow_html=True)
    _xnote = f", other/unknown n={r.n_excluded} excluded" if r.n_excluded else ""
    st.markdown(
        f'<div style="font-size:14px;color:{C["ink"]}">'
        f'Mean gap (F vs M): <b style="color:{_col(mean_gap)}">{mean_gap:+.1f}%</b> &nbsp;·&nbsp; '
        f'Median gap: <b style="color:{_col(median_gap)}">{median_gap:+.1f}%</b> &nbsp;'
        f'<span style="color:{C["muted"]}">(M n={r.n_m}, F n={r.n_f}{_xnote})</span></div>',
        unsafe_allow_html=True)
    st.caption("Positive = women paid more (NL wetsvoorstel: (vrouw-man)/man). " +
               ("Salary read as already full-time-equivalent (source-declared FT) — no extra pro-rating."
                if salary_already_fte
                else "Full-time-equivalent (base ÷ FTE)." if r.fte_normalised
                else "⚠ No FTE column — part-time pay is not pro-rated, which tends to overstate the gap."))

    if adjusted_gap is not None:
        import math as _math
        _ci_ok = adjusted_ci and all(v is not None and not _math.isnan(v) for v in adjusted_ci)
        ci = f" (95% CI {adjusted_ci[0]:+.1f}…{adjusted_ci[1]:+.1f}%)" if _ci_ok else ""
        sig = ("statistically significant" if r.adjusted_significant
               else "not statistically significant" if r.adjusted_significant is False else "significance n/a")
        direction = "more" if (adjusted_gap or 0) >= 0 else "less"
        _extra_controls = list(getattr(r, "adjusted_controls_used", ()) or ())
        _same_as = "function and level" + (f" and {' and '.join(_extra_controls)}" if _extra_controls else "")
        st.markdown(
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-left:3px solid {_col(adjusted_gap)};border-radius:10px;padding:12px 14px;'
            f'margin:10px 0;font-size:13.5px;color:{C["ink"]};line-height:1.55">'
            f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
            f'color:{C["muted"]};margin-bottom:4px">Adjusted — like-for-like</div>'
            f'At the <b>same {_same_as}</b>, women earn '
            f'<b style="color:{_col(adjusted_gap)}">{abs(adjusted_gap):.1f}%</b> {direction} than men'
            f'{ci} — {sig}. The residual "unexplained" gap after controlling for {_same_as}.</div>',
            unsafe_allow_html=True)

    # The grade-assignment regression treats the level column as an ORDERED
    # ladder. Some intake files (e.g. the pay-transparency basis-check
    # template) use "categorie" as NOMINAL comparison-group numbers -- "all
    # employees doing the same work share a group" -- where group 5 is not
    # "higher" than group 3, just different work. Testing whether gender
    # predicts a nominal group NUMBER is statistically meaningless, so let
    # the analyst say which kind this column is instead of silently assuming.
    _is_ladder = st.checkbox(
        "Level/Categorie is an ordered ladder (higher number = more senior) — enables the grade-assignment check",
        value=True, key="lg_level_is_ordinal",
        help="Untick for files where the category is a comparison-GROUP number "
             "(same work grouped together, numbers carry no rank). The pay-gap "
             "figures above are unaffected either way.")
    if r.grade_gap_levels is not None and _is_ladder:
        gg = flip_gap_sign(r.grade_gap_levels)          # positive = women sit at a HIGHER level, on this display
        gg_ci = flip_gap_ci(r.grade_gap_ci)
        gg_sig = ("statistically significant" if r.grade_gap_significant
                  else "not statistically significant" if r.grade_gap_significant is False else "significance n/a")
        gg_dir = "higher" if gg >= 0 else "lower"
        gg_col = C["danger"] if (r.grade_gap_significant and abs(gg) >= 0.5) else C["teal"]
        import math as _math
        _gg_ok = gg_ci and all(v is not None and not _math.isnan(v) for v in gg_ci)
        gg_ci_txt = f" (95% CI {gg_ci[0]:+.2f}…{gg_ci[1]:+.2f})" if _gg_ok else ""
        st.markdown(
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-left:3px solid {gg_col};border-radius:10px;padding:12px 14px;'
            f'margin:10px 0;font-size:13.5px;color:{C["ink"]};line-height:1.55">'
            f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
            f'color:{C["muted"]};margin-bottom:4px">Grade-assignment check</div>'
            f'At the <b>same function</b>, women sit at a level <b style="color:{gg_col}">{abs(gg):.2f}</b> '
            f'{gg_dir} than men{gg_ci_txt} — {gg_sig}. This tests whether <b>gender predicts the level itself</b>, '
            f'not just pay within it — the classification system Art. 4 requires to be gender-neutral, rather than '
            f'assumed. A significant gap here is reason to commission a full job-evaluation review '
            f'(skills, effort, responsibility, working conditions), not proof of one on its own.</div>',
            unsafe_allow_html=True)
    elif r.grade_gap_levels is not None and not _is_ladder:
        st.caption("Grade-assignment check hidden — level read as nominal comparison groups "
                   "(numbers carry no rank), so a \"sits higher/lower\" test doesn't apply. "
                   "Representation per group below still shows where women sit.")

    if r.n_cohorts_tested:
        bcol = C["danger"] if r.n_cohorts_flagged else C["teal"]
        st.markdown(
            f'<div style="font-size:13.5px;color:{C["ink"]};margin:6px 0 4px">'
            f'<b style="color:{bcol}">{r.n_cohorts_flagged} of {r.n_cohorts_tested}</b> Function×Level cohorts '
            f'(with both men and women) show a gap ≥ {DIRECTIVE_THRESHOLD_PCT:.0f}% '
            f'({r.n_cohorts_flagged_reliable} with a reliable ≥{5}-per-gender sample). Under the EU Directive a '
            f'≥5% gap within a category of equal-value work triggers a joint pay assessment unless justified by '
            f'objective, gender-neutral criteria.</div>', unsafe_allow_html=True)

    if r.cohorts:
        tbl = pd.DataFrame([{
            "Function": c.function, "Level": c.level, "M": c.n_m, "F": c.n_f,
            "M median": c.median_m, "F median": c.median_f, "Gap %": flip_gap_sign(c.mean_gap_pct),
            "≥5%?": "⚠ yes" if c.flagged else "no", "Sample": "ok" if c.reliable else "low n",
        } for c in r.cohorts])
        with st.expander(f"Per Function × Level cohort ({len(r.cohorts)} with both men and women)"):
            st.dataframe(tbl, use_container_width=True, hide_index=True)

    with st.expander("Representation — share of women by level and by function"):
        st.caption("A headline gap is usually driven as much by where women sit as by unequal pay within a cohort.")
        cA, cB = st.columns(2)
        cA.dataframe(pd.DataFrame([{"Level": k, "% women": v} for k, v in r.women_by_level.items()]),
                     use_container_width=True, hide_index=True)
        cB.dataframe(pd.DataFrame([{"Function": k, "% women": v} for k, v in r.women_by_function.items()]),
                     use_container_width=True, hide_index=True)

    # ── CAO crosswalk (ISF / CATS®, indicative, public bands only) ─────────
    # This mode has no job titles/reference-library ladder to draw on -- the
    # grade range is this file's own numeric Level column, not an org-wide
    # JobGrade ladder (see the compa-ratio path's version of this for that
    # richer case). No skill/description context here either, by design --
    # this mode doesn't collect that data.
    #
    # GATED ON THE CLIENT'S MARKET. ISF and CATS are Metalektro institutions --
    # Dutch ones -- which is exactly why cao_crosswalk_service encodes them as
    # code rather than data. Rendering them for a Polish client positions their
    # grades onto Dutch salarisgroepen beside euro monthly scales, which implies
    # a legal classification that does not apply to them. Germany's ERA and
    # France's conventions collectives are different institutions, not different
    # numbers, so each becomes its own module rather than a translated label.
    _lvl_num = pd.to_numeric(df[level_col], errors="coerce")
    if _is_dutch_client() and _lvl_num.notna().mean() > 0.9:
        try:
            from services.cao_crosswalk_service import (
                crosswalk_to_cats, crosswalk_to_isf, isf_indicator, known_cats_sectors)
        except ImportError:
            from jobsy.services.cao_crosswalk_service import (
                crosswalk_to_cats, crosswalk_to_isf, isf_indicator, known_cats_sectors)

        st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">'
                    f'CAO crosswalk — ISF / CATS® (indicative)</div>', unsafe_allow_html=True)
        st.caption("Positions this file's own Level column against the PUBLIC salary-group structure "
                   "of a sector CAO — never a reproduced ISF/CATS® scoring method (FME's / De Leeuw "
                   "Consult's protected IP; see docs/cao-metalektro-isf-reference.md). Always "
                   "indicative — official classification needs a certified weging.")

        lg_min, lg_max = float(_lvl_num.min()), float(_lvl_num.max())
        st.caption(f"Rank-positioned against this file's own Level range: {lg_min:g}–{lg_max:g} "
                   "(no reference-library grade ladder available in this mode).")

        _lsys = st.radio("CAO systeem", ["ISF (Metalektro)", "CATS® (kies sector)"],
                         key="lg_cao_system", horizontal=True)
        cw = pd.DataFrame({function_col: df[function_col], level_col: df[level_col],
                           "_lvl_num": _lvl_num,
                           "_pay": pd.to_numeric(df[salary_col], errors="coerce")})
        cw = cw[cw["_lvl_num"].notna()]

        if _lsys.startswith("ISF"):
            # THE SAME TREATMENT AS THE MATCHED PATH. This half of the page used
            # to print a bare salarisgroep while the other half qualified the
            # identical claim with an overlap and a scope — one screen making a
            # flat assertion and a careful one at the same time.
            #
            # There is no grade ladder here and no library band, so the second
            # basis cannot exist. What this mode DOES have is the file's own
            # salaries, so the overlap is measured against what the client
            # actually pays that cohort — a different source from the matched
            # path's salary band, and labelled as such rather than blended.
            _cohort_pay = (cw.dropna(subset=["_pay"])
                             .groupby([function_col, level_col])["_pay"]
                             .agg(["min", "max"]).to_dict("index"))

            def _isf_row(row):
                key = (row[function_col], row[level_col])
                span = _cohort_pay.get(key)
                pay = (float(span["min"]), float(span["max"])) if span else None
                ind = isf_indicator(row["_lvl_num"], lg_min, lg_max, our_pay=pay)
                if ind.indicated_group is None:
                    return ("— buiten bereik", "—", ind.overlap_reason.split(".")[0])
                overlap = (f"{ind.pay_overlap_pct:g}%" if ind.pay_overlap_pct is not None
                           else "— (geen gepubliceerde schaal)")
                scale = (f"{_money(ind.published_scale[0])}–{_money(ind.published_scale[1])}"
                         if ind.published_scale else "— (Hoger Personeel)")
                return (ind.indicated_group, overlap, scale)

            cw[["Indicatief ISF", "Loonoverlap", "ISF-schaal (jaar)"]] = cw.apply(
                lambda r: pd.Series(_isf_row(r)), axis=1)
            _groups = sorted(g for g in cw["Indicatief ISF"].dropna().unique())
            _pick = st.multiselect("Filter op salarisgroep", _groups, default=_groups, key="lg_isf_group_filter")
            _shown = cw[cw["Indicatief ISF"].isin(_pick)]
            st.dataframe(_shown[[function_col, level_col, "Indicatief ISF", "Loonoverlap", "ISF-schaal (jaar)"]],
                        use_container_width=True, hide_index=True)
            st.caption("Indicatief: positionering binnen de publieke ISF-bandbreedtes — geen berekende "
                       "ISF-score. Officiële ISF-indeling vereist een gecertificeerde weging. "
                       "**Loonoverlap** is hier gemeten tegen het loon dat in dít bestand aan die "
                       "Functie × Niveau wordt betaald (niet tegen een loonband uit de bibliotheek — "
                       "die is in deze modus niet beschikbaar). Er is geen tweede positioneringsbasis: "
                       "zonder gradenladder bestaat er geen puntenbereik om mee te vergelijken.")
        else:
            _sector = st.selectbox("Sector (CATS® handboek)", known_cats_sectors(), key="lg_cats_sector")
            def _cats_row(lv):
                res = crosswalk_to_cats(lv, lg_min, lg_max, sector=_sector)
                return (res.functiegroep, res.salarisgroep)
            cw[["Functiegroep", "Salarisgroep"]] = cw["_lvl_num"].apply(lambda v: pd.Series(_cats_row(v)))
            _groups = sorted(g for g in cw["Salarisgroep"].dropna().unique())
            _pick = st.multiselect("Filter op salarisgroep", _groups, default=_groups, key="lg_cats_group_filter")
            _shown = cw[cw["Salarisgroep"].isin(_pick)]
            st.dataframe(_shown[[function_col, level_col, "Functiegroep", "Salarisgroep"]],
                        use_container_width=True, hide_index=True)
            st.caption(f"Label alignment only, {_sector} — CATS® has no public point-range table to "
                       "position against (unlike ISF). Official classification requires reading the "
                       "sector's niveaublad for the relevant functiefamilie, done by a certified CATS® user.")
    else:
        st.caption("CAO crosswalk skipped — Level column isn't numeric/ordinal enough to position "
                   "(need e.g. 1-12, not free-text grades).")

    for note in r.notes:
        st.caption("· " + note)

    # ── shift-toeslag & generatiepact reasoning ─────────────────────────
    try:
        from services.special_conditions_service import analyze_special_conditions
    except ImportError:
        from jobsy.services.special_conditions_service import analyze_special_conditions
    _sc = analyze_special_conditions(
        df, function_col=function_col, level_col=level_col, gender_col=gender_col,
        salary_col=salary_col, fte_col=fte_col, tenure_col=tenure_col,
        salary_already_fte=salary_already_fte)
    if _sc is not None and (_sc.n_shift_tagged or _sc.n_generatiepact):
        st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;color:{C["muted"]};margin:22px 0 6px">'
                    f'Shift-work &amp; generatiepact reasoning</div>', unsafe_allow_html=True)
        st.caption(f"Free-text conditions column detected: **{_sc.conditions_col}**. Shift (ploeg) "
                   "toeslag and generatiepact reduced-hours rows are flagged and re-tested for how much "
                   "they move the headline gap — the numbers alone can't say whether either mechanism is "
                   "already folded into the salary column, so this shows sensitivity, not a silent correction.")
        for _f in _sc.risk_flags:
            st.markdown(
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                f'border-left:3px solid {C["teal"] if _f.startswith("No ") else C["danger"]};'
                f'border-radius:10px;padding:10px 14px;margin:6px 0;font-size:13px;'
                f'color:{C["ink"]};line-height:1.5">{_f}</div>', unsafe_allow_html=True)
        if _sc.scenarios:
            _sctbl = pd.DataFrame([{
                "Scenario": s.label, "N": s.n, "M": s.n_m, "F": s.n_f,
                "Mean gap %": s.mean_gap_pct, "Adjusted gap %": s.adjusted_gap_pct,
            } for s in _sc.scenarios])
            st.dataframe(_sctbl, use_container_width=True, hide_index=True)
            _base = _sc.scenarios[0]
            _worst = max(_sc.scenarios[1:], key=lambda s: abs((s.mean_gap_pct or 0) - (_base.mean_gap_pct or 0)),
                        default=None)
            if _worst is not None and _base.mean_gap_pct is not None and _worst.mean_gap_pct is not None:
                _delta = _worst.mean_gap_pct - _base.mean_gap_pct
                st.caption(f"Most sensitive to: **{_worst.label}** — mean gap moves "
                           f"{_delta:+.1f} percentage points once those rows are set aside. "
                           "Treat the headline number as a range bounded by these scenarios until the "
                           "underlying mechanism is confirmed with payroll/HR.")
        if _sc.next_steps:
            st.markdown(f'<div style="font-size:13px;color:{C["ink"]};margin:10px 0 2px;font-weight:600">'
                        f'Advised next steps</div>', unsafe_allow_html=True)
            for _s in _sc.next_steps:
                st.markdown(f'<div style="font-size:13px;color:{C["muted"]};margin:2px 0 2px 4px">— {_s}</div>',
                           unsafe_allow_html=True)

    # ── variable-pay exposure ───────────────────────────────────────────
    # Everything above measures one salary column. The Directive's "pay" also
    # covers complementary and variable components, and a gap can live entirely
    # in who is ELIGIBLE for a bonus rather than in anyone's base — which no
    # amount of looking at base pay will ever show.
    #
    # The compa-ratio view can already report that when a client supplies
    # bonus/allowance/LTI columns. Most cannot. But once a grid is leveled,
    # PayMix states what each Function × Level is entitled to, on exactly the
    # key this page already groups by — so the structural half is answerable
    # from data the client has already handed over.
    # The typed record, not the frame: PayMix is on the Repository since it
    # joined the library, and one fact reachable two ways is how two halves of
    # a screen end up disagreeing.
    _repo_pe = getattr(catalog, "repository", None)
    _paymix = getattr(_repo_pe, "pay_mix", None) if _repo_pe is not None else None
    if _paymix:
        try:
            from services.pay_equity_service import analyze_variable_pay_exposure
        except ImportError:
            from jobsy.services.pay_equity_service import analyze_variable_pay_exposure
        try:
            _ex = analyze_variable_pay_exposure(
                df, _paymix, function_col=function_col, level_col=level_col,
                gender_col=gender_col, salary_col=salary_col, fte_col=fte_col,
                salary_already_fte=salary_already_fte)
        except Exception as _exc:
            _ex = None
            st.caption(f"Variable-pay exposure unavailable: {_exc}")

        if _ex is not None:
            st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                        f'text-transform:uppercase;color:{C["muted"]};margin:20px 0 6px">'
                        f'Variable-pay exposure · policy entitlement</div>', unsafe_allow_html=True)

            if _ex.pct_women_lti_eligible is None:
                st.caption("Not enough people of one gender with a known entitlement to report "
                           "exposure without re-identifying them.")
            elif _ex.widening_pp is None:
                st.caption("Entitlement is shown below, but the gap it implies could not be "
                           "computed from these salaries.")
            else:
                # This page states gaps as (woman − man)/man, so a structure that
                # favours men has to read NEGATIVE here like every other figure
                # on screen. widening_pp is men-ahead, hence the flip.
                _base = flip_gap_sign(_ex.base_mean_gap_pct)
                _tot = flip_gap_sign(_ex.implied_total_mean_gap_pct)
                _shift = None if _base is None or _tot is None else _tot - _base
                _scol = C["danger"] if _ex.structure_widens_gap else C["teal"]
                st.markdown(
                    f'<div style="font-size:14px;color:{C["ink"]}">'
                    f'Base pay: <b>{_base:+.1f}%</b> &nbsp;→&nbsp; '
                    f'on-target total pay: <b style="color:{_scol}">{_tot:+.1f}%</b> &nbsp;·&nbsp; '
                    f'the pay structure moves the gap by <b style="color:{_scol}">{_shift:+.1f} pp</b>'
                    f'</div>', unsafe_allow_html=True)

                _tiles = [
                    ("Target variable · women", f"{_ex.mean_target_var_f:.1f}%", C["ink"]),
                    ("Target variable · men", f"{_ex.mean_target_var_m:.1f}%", C["ink"]),
                    ("LTI-eligible · women", f"{_ex.pct_women_lti_eligible:.0f}%",
                     C["danger"] if (_ex.lti_access_gap_pp or 0) > 0 else C["ink"]),
                    ("LTI-eligible · men", f"{_ex.pct_men_lti_eligible:.0f}%", C["ink"]),
                ]
                _trow = "".join(
                    f'<div style="flex:1;min-width:120px;background:{C["surface"]};border:1px solid {C["line"]};'
                    f'border-radius:12px;padding:12px 14px">'
                    f'<div style="font-family:{FONT_SERIF};font-size:26px;font-weight:700;color:{col}">{val}</div>'
                    f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.08em;'
                    f'text-transform:uppercase;color:{C["muted"]};margin-top:2px">{lab}</div></div>'
                    for lab, val, col in _tiles)
                st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 4px">'
                            f'{_trow}</div>', unsafe_allow_html=True)

                with st.expander("Entitlement by cohort"):
                    st.dataframe(pd.DataFrame([{
                        "Function": c.function, "Level": c.level,
                        "Men": c.n_m, "Women": c.n_f,
                        "Target variable": f"{c.target_variable_pct:.0f}%",
                        "13th month": f"{c.thirteenth_month_pct:.2f}%",
                        "LTI": "Yes" if c.lti_eligible else "—",
                    } for c in _ex.cohorts]), use_container_width=True, hide_index=True)

            for _n in _ex.notes:
                st.caption(_n)

    try:
        from services.pay_equity_export_service import PayEquityExportService
    except ImportError:
        from jobsy.services.pay_equity_export_service import PayEquityExportService
    _report_lang = st.radio("Report language", ["English", "Nederlands"],
                           key="lg_report_lang", horizontal=True)
    _lang_code = "nl" if _report_lang == "Nederlands" else "en"
    _report_bytes = PayEquityExportService().to_workbook_bytes(r, lang=_lang_code)
    _logged_download(
        "⬇ Download pay equity report (.xlsx)" if _lang_code == "en"
        else "⬇ Download loonkloofrapport (.xlsx)",
        _report_bytes,
        file_name=f"jobsy_pay_equity_report_{_lang_code}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def pay_equity_page(catalog, service):
    """Compa-ratio & pay-position analysis vs the role bands (EU pay transparency)."""
    import pandas as _pd, io as _io, re as _re
    repo = catalog.repository
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Pay Equity</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Upload actual salaries to see each person\'s <b>compa-ratio</b> (pay ÷ band midpoint) '
        f'and range position, plus a light <b>EU Pay Transparency Directive</b> read-out: '
        f'mean &amp; median gender gaps on base and total pay (full-time-equivalent), '
        f'per-category testing against the 5% threshold, pay-quartile split and who receives variable pay. '
        f'Below-range pay is flagged.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-left:3px solid {C["amber"]};'
        f'border-radius:10px;padding:12px 14px;margin:0 0 16px;font-size:13px;color:{C["muted"]};line-height:1.55">'
        f'<b style="color:{C["ink"]}">Where this stands legally right now:</b> Dutch implementing legislation for '
        f'the Directive is not yet in force — the bill was only submitted to the Tweede Kamer in May 2026, '
        f'targeted for 1 January 2027 (later than the original June 2026 EU deadline, which the European '
        f'Commission declined to extend). Once live, the formal reporting duty that starts the Directive\'s '
        f'6-month remediation clock is phased by employer size: <b>150+ employees</b> first report 7 June 2028 '
        f'(annually after); <b>100–149</b> first report 7 June 2031 (every 3 years); <b>under 100</b> has no '
        f'reporting duty under this mechanism at all. Read everything below as getting ahead of the law, not '
        f'as a live compliance deadline — unless the client is already at 150+ employees.</div>',
        unsafe_allow_html=True,
    )
    # template
    tmpl = _pd.DataFrame([
        {"EmployeeID": "E1001", "Name": "Alex de Vries", "JobTitle": "Software Engineer", "ActualSalary": 68000, "Gender": "F"},
        {"EmployeeID": "E1002", "Name": "Sam Jansen", "JobTitle": "Head of Sales", "ActualSalary": 118000, "Gender": "M"},
    ])
    _b = _io.BytesIO(); tmpl.to_excel(_b, index=False)
    _template_download("⬇ Download pay template (.xlsx)", _b.getvalue(),
        file_name="jobsy_pay_equity_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    _salkeys = {"actualsalary", "actual salary", "salary", "base salary", "basesalary", "grosssalary",
                "gross salary", "salaris", "brutosalaris", "loon", "pay"}
    _salcont = ["sal", "salaris", "loon", "pay", "bruto"]
    # #2 — reuse the workforce file already uploaded on the Matching page if it carries pay
    df = None
    wf = st.session_state.get("upload_df")
    if wf is not None and _smart_detect(list(wf.columns), _salkeys, _salcont):
        if st.checkbox(f"Use the workforce data uploaded on Matching ({len(wf)} rows, has pay)", value=True):
            df = wf.copy()
    if df is None:
        up = st.file_uploader("Upload actual pay (.csv or .xlsx)", type=["csv", "xls", "xlsx"], key="pe_up")
        if not up:
            st.markdown(
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-radius:12px;'
                f'padding:16px;color:{C["muted"]};font-size:14px;margin-top:6px">'
                f'Provide columns for job title and actual annual base salary; optionally name, gender, and '
                f'variable pay (Bonus, Allowances, LTI) for the total-pay gender gap.</div>',
                unsafe_allow_html=True)
            return
        try:
            df = _pd.read_csv(up) if up.name.endswith(".csv") else _pd.read_excel(up)
        except Exception as exc:
            st.error(f"Could not read file: {exc}"); return
    if df is None or df.empty:
        st.warning("No usable data."); return

    cols = list(df.columns)
    # ── Option A: leveled-grid path — client already provides Function + Level ──
    # If both are present we can run the band-free structural gender pay gap
    # directly (no job-title matching needed). Offer it as the primary mode.
    _fun_col = _smart_detect(cols, {"function", "functie", "jobfamily", "job family", "family",
                                    "functiefamilie", "discipline", "vakgebied"},
                             ["function", "functie", "family", "discipline"])
    _lvl_col = _smart_detect(cols, {"level", "niveau", "grade", "joblevel", "job level", "career level",
                                    "functieniveau", "schaal", "salarisschaal",
                                    "categorie", "category", "werknemerscategorie", "functiegroep"},
                             ["level", "niveau", "grade", "schaal", "categorie", "category"])
    if _fun_col and _lvl_col:
        _mode = st.radio(
            "This file is already leveled (Function + Level detected) — how should Pay Equity read it?",
            ["Structural gender pay gap on Function × Level — no job titles or bands needed",
             "Match job titles to salary bands (compa-ratio)"],
            key="pe_mode",
        )
        if _mode.startswith("Structural"):
            _lg_gender = _smart_detect(cols, {"gender", "geslacht", "sex", "m/v", "m/f"},
                                       ["gender", "geslacht", "sex"])
            _lg_fte = _smart_detect(cols, {"fte", "parttime", "part-time", "part time", "werkuren", "deeltijd",
                                           "contract hours", "hours", "parttimefactor", "deeltijdfactor"},
                                    ["fte", "parttime", "deeltijd"])
            _lg_tenure = _smart_detect(cols, {"tenure", "yearsofservice", "years of service", "dienstjaren",
                                              "startdate", "start date", "hiredate", "hire date", "indiensttreding",
                                              "datum in dienst"},
                                       ["tenure", "dienstjaren", "startdate", "hiredate", "indiensttreding"])
            _lg_age = _smart_detect(cols, {"age", "leeftijd", "birthdate", "birth date", "dateofbirth",
                                          "date of birth", "geboortedatum"},
                                    ["age", "leeftijd", "birthdate", "geboortedatum"])
            _lg_sal = _smart_detect(cols, _salkeys, _salcont)
            # "FT salaris" (Dutch intake templates) means the column is ALREADY
            # full-time-equivalent. Dividing it by FTE again double-corrects --
            # part-timers (mostly women, in NL) get inflated pay and a real gap
            # silently shrinks. Default from the column name; analyst can override.
            _looks_fte = bool(_lg_sal) and bool(_re.search(r"(^|\W)(ft|fte|fulltime|full-time|voltijd)($|\W)",
                                                            str(_lg_sal), _re.I))
            _sal_reading = st.radio(
                "How should the salary column be read?",
                ["Already full-time-equivalent (do not divide by FTE)",
                 "Actual paid salary (divide by FTE to compare)"],
                index=(0 if _looks_fte else 1), key="lg_sal_reading", horizontal=False)
            _already_fte = _sal_reading.startswith("Already")
            _render_leveled_gap(df, function_col=_fun_col, level_col=_lvl_col, gender_col=_lg_gender,
                                salary_col=_lg_sal, fte_col=(None if _already_fte else _lg_fte),
                                tenure_col=_lg_tenure, age_col=_lg_age, salary_already_fte=_already_fte,
                                catalog=catalog)
            return
    title_col = _smart_detect(cols, {"jobtitle", "job title", "title", "currentrole", "current role",
                                     "functie", "functietitel", "role"}, ["title", "functie", "role"]) or cols[0]
    sal_col = _smart_detect(cols, _salkeys, _salcont)
    name_col = _smart_detect(cols, {"name", "fullname", "full name", "naam", "employee", "medewerker"}, ["name", "naam"])
    gender_col = _smart_detect(cols, {"gender", "geslacht", "sex", "m/v", "m/f"}, ["gender", "geslacht", "sex"])
    bonus_col = _smart_detect(cols, {"bonus", "variable pay", "variable", "incentive", "commission",
                                     "bonus/commission"}, ["bonus", "incentive", "commission", "variable"])
    allow_col = _smart_detect(cols, {"allowances", "allowance", "toeslag", "toeslagen", "vergoeding",
                                     "13th month", "holiday allowance", "vakantiegeld"},
                              ["allowance", "toeslag", "vergoeding", "vakantiegeld"])
    lti_col = _smart_detect(cols, {"lti", "equity", "long-term incentive", "long term incentive", "rsu",
                                   "stock", "aandelen", "options", "share plan"}, ["lti", "equity", "rsu", "aandelen"])
    fte_col = _smart_detect(cols, {"fte", "parttime", "part-time", "part time", "werkuren", "deeltijd",
                                   "contract hours", "hours", "parttimefactor", "deeltijdfactor"},
                            ["fte", "parttime", "deeltijd"])
    comp_cols = {"Bonus": bonus_col, "Allowances": allow_col, "LTI": lti_col}
    has_variable = any(comp_cols.values())

    # PayElements marks which components are statutory in the Netherlands. The
    # library has carried those flags all along and nothing asked them anything.
    # What they can answer is a question about the FILE, never about the
    # employer: a missing column means this analysis cannot see that component,
    # not that it was not paid.
    try:
        from services import pay_components_service as _payc
        _repo_sc = getattr(catalog, "repository", None)
        _present = {
            "PE-HOL": bool(allow_col),      # holiday allowance arrives inside allowances
            "PE-13": bool(allow_col),
            "PE-VAR": bool(bonus_col),
            "PE-LTI": bool(lti_col),
        }
        _cov = _payc.statutory_coverage(_repo_sc, _present) if _repo_sc else []
        _absent = [e for e, seen in _cov if not seen]
        if _absent:
            st.caption(
                "Statutory in the Netherlands and not visible in this file: "
                + ", ".join(f"**{e.name}** ({e.typical_value})" for e in _absent)
                + ". The Directive reports on total pay, so a component this file does not "
                  "carry is a component the gap below cannot see — which is a limit of the "
                  "upload, not a finding about the employer.")
    except Exception:
        pass
    if not sal_col:
        st.error("No salary column found. Include an 'ActualSalary' column."); return
    _detected = [("Title", title_col), ("Salary", sal_col), ("Name", name_col), ("Gender", gender_col),
                 ("FTE", fte_col), ("Bonus", bonus_col), ("Allowances", allow_col), ("LTI", lti_col)]
    st.caption(" · ".join(f"{lab}: **{c}**" for lab, c in _detected if c))

    def _num(v):
        s = _re.sub(r"[^\d]", "", str(v))
        return int(s) if s else None

    def _fnum(v):
        # Parse an FTE / part-time factor: accepts 1.0 / 0.8 / "0,8" / "80%" / 80.
        try:
            s = _re.sub(r"[^\d.]", "", str(v).strip().replace(",", ".").replace("%", ""))
            f = float(s) if s else None
        except Exception:
            f = None
        if f is None or f <= 0:
            return None
        if f > 2:            # given as a percentage (e.g. 80) → 0.80
            f = f / 100.0
        return round(f, 4) if f <= 1.5 else None

    rows = []
    for _, r in df.iterrows():
        actual = _num(r.get(sal_col))
        if actual is None:
            continue
        title = str(r.get(title_col, "")).strip()
        m = service.match(title)
        band = repo.salary.get((m.function, m.level)) if m.matched else None
        rec = {"Name": (str(r.get(name_col)) if name_col else str(r.get(cols[0]))),
               "Input title": title, "Matched role": m.standard_title or "— no match —",
               "Function": m.function or "", "Level": m.level or "—", "Actual": actual,
               "JobId": m.job_id, "Description": m.description or ""}
        _fte = _fnum(r.get(fte_col)) if fte_col else None
        rec["FTE"] = _fte if _fte else 1.0
        rec["Actual FT"] = round(actual / rec["FTE"]) if rec["FTE"] else actual
        if gender_col:
            rec["Gender"] = str(r.get(gender_col, "")).strip().upper()[:1]
            # Dutch M/V: read V(rouw) as F so a Dutch export analyses natively.
            if rec["Gender"] == "V":
                rec["Gender"] = "F"
        if has_variable:
            _bonus = (_num(r.get(bonus_col)) or 0) if bonus_col else 0
            _allow = (_num(r.get(allow_col)) or 0) if allow_col else 0
            _lti = (_num(r.get(lti_col)) or 0) if lti_col else 0
            rec["Bonus"] = _bonus; rec["Allowances"] = _allow; rec["LTI"] = _lti
            rec["Total cash"] = actual + _bonus + _allow
            rec["Total pay"] = actual + _bonus + _allow + _lti
            rec["Total pay FT"] = round((actual + _bonus + _allow + _lti) / rec["FTE"]) if rec["FTE"] else (actual + _bonus + _allow + _lti)
        # Placement against the band lives in salary_service, and it compares
        # full-time equivalents when an FTE column was supplied -- the band is a
        # full-time band, and the Data Readiness panel promises the pro-rating.
        pos = _salary.position(actual, band, rec["FTE"] if fte_col else None)
        rec["Band P50"] = pos.band_p50
        rec["Band min"] = pos.band_min
        rec["Band max"] = pos.band_max
        rec["Grade"] = pos.grade
        rec["Compa-ratio"] = pos.compa_ratio
        rec["Range %"] = pos.range_penetration
        rec["Status"] = pos.status
        rows.append(rec)
    if not rows:
        st.warning("No usable rows (need a numeric salary)."); return
    res = _pd.DataFrame(rows)
    priced = res[res["Compa-ratio"].notna()]

    # coverage / exclusions (transparency — excluded rows silently leave the figures)
    _coverage = _salary.Coverage(uploaded=len(df), parsed=len(res), priced=len(priced))
    st.caption(_coverage.message())
    # Say which pay was compared, rather than leaving the reader to assume.
    _prorated = int(res["FTE"].ne(1.0).sum()) if fte_col and "FTE" in res.columns else 0
    st.caption(
        f"Compa-ratio and range position are compared full-time-equivalent (base ÷ FTE); "
        f"{_prorated} part-time salaries were pro-rated to the full-time band."
        if _prorated else
        "Compa-ratio and range position use the salary as supplied. Bands are full-time, "
        "so without an FTE column part-timers read as underpaid.")

    # ── headline tiles ──────────────────────────────────────────────────
    avg_compa = round(priced["Compa-ratio"].mean(), 2) if len(priced) else 0
    below = int((res["Status"] == "Below range").sum())
    above = int((res["Status"] == "Above range").sum())
    nomatch = int((res["Status"] == "No match").sum())
    tiles = [("Employees priced", str(len(priced)), C["ink"]),
             ("Avg compa-ratio", f"{avg_compa:.2f}", C["teal"] if 0.95 <= avg_compa <= 1.05 else C["amber"]),
             ("Below range", str(below), C["danger"] if below else C["ink"]),
             ("Above range", str(above), C["blue"] if above else C["ink"]),
             ("Unmatched", str(nomatch), C["amber"] if nomatch else C["ink"])]
    trow = "".join(
        f'<div style="flex:1;min-width:110px;background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-radius:12px;padding:14px 16px"><div style="font-family:{FONT_SERIF};font-size:28px;'
        f'font-weight:700;color:{col}">{val}</div><div style="font-family:{FONT_MONO};font-size:10px;'
        f'letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]};margin-top:2px">{lab}</div></div>'
        for lab, val, col in tiles)
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 16px">{trow}</div>',
                unsafe_allow_html=True)

    # ── compa-ratio scatter ─────────────────────────────────────────────
    STATUS_COLOR = {"Below range": "#E0555F", "Below market": "#D9932B", "At market": "#0E9E7E",
                    "Above market": "#67E8F9", "Above range": "#A87CFF", "No match": "#8A93A5"}
    if len(priced):
        try:
            import altair as _alt
            ch = _pd.DataFrame({
                "Compa-ratio": priced["Compa-ratio"], "Role": priced["Matched role"],
                "Name": priced["Name"], "Actual": priced["Actual"], "Status": priced["Status"]})
            pts = _alt.Chart(ch).mark_circle(size=110, opacity=0.85).encode(
                x=_alt.X("Compa-ratio:Q", scale=_alt.Scale(zero=False), title="Compa-ratio (pay ÷ band midpoint)"),
                y=_alt.Y("Role:N", title=None),
                color=_alt.Color("Status:N", scale=_alt.Scale(domain=list(STATUS_COLOR), range=list(STATUS_COLOR.values())), legend=_alt.Legend(orient="bottom")),
                tooltip=["Name", "Role", _alt.Tooltip("Actual:Q", format=",.0f"), "Compa-ratio", "Status"])
            rule = _alt.Chart(_pd.DataFrame({"x": [1.0]})).mark_rule(color="#8A93A5", strokeDash=[4, 4]).encode(x="x:Q")
            chart = (rule + pts).properties(height=max(220, 26 * ch["Role"].nunique())).configure_view(strokeOpacity=0).configure_axis(labelColor="#B9A6DD", titleColor="#B9A6DD", gridColor="#FFFFFF14").configure_legend(labelColor="#B9A6DD", titleColor="#B9A6DD")
            st.altair_chart(chart, use_container_width=True)
        except Exception:
            pass

    # ── CAO crosswalk (ISF / CATS®, indicative, public bands only) ─────────
    # Gated on the client's market -- see _is_dutch_client().
    if _is_dutch_client() and len(priced) and priced["Grade"].notna().any():
        try:
            from services.cao_crosswalk_service import (
                crosswalk_to_cats, crosswalk_to_isf, isf_indicator, known_cats_sectors)
        except ImportError:
            from jobsy.services.cao_crosswalk_service import (
                crosswalk_to_cats, crosswalk_to_isf, isf_indicator, known_cats_sectors)

        st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">'
                    f'CAO crosswalk — ISF / CATS® (indicative)</div>', unsafe_allow_html=True)
        st.caption(f"Positions {_brand_name()}'s own grade against the PUBLIC salary-group structure of a "
                   "sector CAO — never a reproduced ISF/CATS® scoring method (that's FME's / De "
                   "Leeuw Consult's protected IP; see docs/cao-metalektro-isf-reference.md). "
                   "Always indicative — official classification needs a certified weging.")

        graded = priced[priced["Grade"].notna()].copy()
        grade_min_repo = min(repo.job_grades.keys()) if getattr(repo, "job_grades", None) else None
        grade_max_repo = max(repo.job_grades.keys()) if getattr(repo, "job_grades", None) else None
        g_min = grade_min_repo if grade_min_repo is not None else float(graded["Grade"].min())
        g_max = grade_max_repo if grade_max_repo is not None else float(graded["Grade"].max())
        _range_src = "org's full JobGrade ladder" if grade_min_repo is not None else "this file's own grade range"

        # The ladder's own point ranges, where the library has them. They give a
        # truer position than the grade number, because the rungs are not evenly
        # spaced -- grade 3 spans 35 points and grade 14 spans 530. They are OUR
        # points on OUR scale and are never looked up in the ISF table; see
        # cao_crosswalk_service._position.
        _grades = getattr(repo, "job_grades", None) or {}
        _pts = {g: gr.hay_mid for g, gr in _grades.items() if gr.hay_mid}
        _pt_min = min((gr.hay_min for gr in _grades.values() if gr.hay_min), default=None)
        _pt_max = max((gr.hay_max for gr in _grades.values() if gr.hay_max), default=None)
        _has_points = bool(_pts) and _pt_min is not None and _pt_max is not None and _pt_max > _pt_min

        def _pt(grade):
            try:
                return _pts.get(int(float(grade)))
            except (TypeError, ValueError):
                return None

        # DEFAULT STAYS GRADE RANK, deliberately. The ladder's point ranges are
        # real and were read by nothing until now, but they are OUR scale
        # (100-1800) and ISF's sequence is theirs. Carrying a proportion across
        # assumes their bands are evenly spaced in points, which cannot be
        # checked without the method that is precisely the protected part. On
        # the real ladder the two bases disagree on thirteen of fourteen grades,
        # so making points the default would silently move a client-facing
        # figure on an assumption. It is offered, labelled, and compared.
        # NEITHER BASIS IS PICKED. Both are reported, next to a measured overlap
        # and the scope, because the choice between them was the wrong question:
        # both stretch our ladder onto ISF's sequence end to end, and the two
        # do not cover the same jobs. Our grade is the answer; ISF is an
        # indicator carrying the quality of its own reading.
        st.caption(
            f"**Our grade is the classification.** It is our own gender-neutral system, and it is "
            f"what this analysis runs on. The ISF column beside it is an *indicator* — where a job "
            f"would sit in the sector CAO — with the quality of that reading attached, never a "
            f"substitute for a certified weging."
            + (f" Positioned against the {_range_src} (grade {g_min:g}–{g_max:g}), by grade rank and "
               f"by each grade's own point range ({_pt_min:g}–{_pt_max:g}); both are shown."
               if _has_points else
               f" Positioned against the {_range_src}: grade {g_min:g}–{g_max:g}."))

        _system = st.radio("CAO systeem", ["ISF (Metalektro)", "CATS® (kies sector)"],
                           key="cao_crosswalk_system", horizontal=True)

        if _system.startswith("ISF"):
            def _isf_row(row):
                grade = row["Grade"]
                pay = None
                _lo, _hi = row.get("Band min"), row.get("Band max")
                try:
                    if _lo is not None and _hi is not None and not _pd.isna(_lo) and not _pd.isna(_hi):
                        pay = (float(_lo), float(_hi))
                except (TypeError, ValueError):
                    pay = None
                ind = isf_indicator(grade, g_min, g_max, our_pay=pay,
                                    points=_pt(grade) if _has_points else None,
                                    points_min=_pt_min, points_max=_pt_max)
                if ind.indicated_group is None:
                    return ("— buiten bereik", "—", "—", ind.overlap_reason.split(".")[0])
                agree = ("beide gelijk" if ind.bases_agree
                         else (f"{ind.group_by_rank} / {ind.group_by_points}"
                               if ind.bases_agree is False else "—"))
                overlap = (f"{ind.pay_overlap_pct:g}%" if ind.pay_overlap_pct is not None
                           else "— (geen gepubliceerde schaal)")
                scale = (f"{_money(ind.published_scale[0])}–{_money(ind.published_scale[1])}"
                         if ind.published_scale else "— (Hoger Personeel)")
                return (ind.indicated_group, agree, overlap, scale)

            graded[["Indicatief ISF", "Rang / punten", "Loonoverlap", "ISF-schaal (jaar)"]] =                 graded.apply(lambda r: _pd.Series(_isf_row(r)), axis=1)
            _groups = sorted(g for g in graded["Indicatief ISF"].dropna().unique())
            _pick = st.multiselect("Filter op salarisgroep", _groups, default=_groups, key="isf_group_filter")
            _shown = graded[graded["Indicatief ISF"].isin(_pick)]
            st.dataframe(_shown[["Name", "Matched role", "Function", "Level", "Grade",
                                 "Indicatief ISF", "Rang / punten", "Loonoverlap", "ISF-schaal (jaar)"]],
                        use_container_width=True, hide_index=True)
            st.caption(
                "**Loonoverlap** is het enige percentage hier, en het is een meting: welk deel van "
                "onze eigen loonbandbreedte binnen de gepubliceerde schaal van die groep valt. "
                "Laag betekent dat de letter weinig zegt. **Rang / punten** toont beide "
                "positioneringen apart — waar ze verschillen, vertelt dat verschil iets. Er is "
                "bewust géén samengestelde betrouwbaarheidsscore: die zou een precisie suggereren "
                "die geen van de onderdelen heeft.")
            st.caption(f"Indicatief: positionering van {_brand_name()}'s eigen gradering binnen de publieke "
                       "ISF-bandbreedtes — geen berekende ISF-score. Officiële ISF-indeling vereist "
                       "een gecertificeerde weging.")
            if _has_points:
                _other = {}
                for _g in sorted(_pts):
                    _a = crosswalk_to_isf(_g, g_min, g_max)
                    _b = crosswalk_to_isf(_g, g_min, g_max, points=_pts[_g],
                                          points_min=_pt_min, points_max=_pt_max)
                    if _a and _b and _a.salarisgroep != _b.salarisgroep:
                        _other[_g] = (_a.salarisgroep, _b.salarisgroep)
                if _other:
                    st.caption(
                        f"The two bases disagree on {len(_other)} of {len(_pts)} grades — e.g. grade "
                        + ", ".join(f"{g} ({a} by rank, {b} by points)"
                                    for g, (a, b) in list(_other.items())[:3])
                        + ". That disagreement is the ladder's own spacing telling you something, "
                          "not one of them being wrong.")
        else:
            _sector = st.selectbox("Sector (CATS® handboek)", known_cats_sectors(), key="cats_sector")
            def _cats_row(grade):
                # Rank only, and not an oversight: CATS publishes no point
                # table and no salary scale, so there is neither a second basis
                # to compare against nor an overlap to measure. The note the
                # service returns says exactly that.
                r = crosswalk_to_cats(grade, g_min, g_max, sector=_sector)
                return (r.functiegroep, r.salarisgroep)
            graded[["Functiegroep", "Salarisgroep"]] = graded["Grade"].apply(lambda g: _pd.Series(_cats_row(g)))
            _groups = sorted(g for g in graded["Salarisgroep"].dropna().unique())
            _pick = st.multiselect("Filter op salarisgroep", _groups, default=_groups, key="cats_group_filter")
            _shown = graded[graded["Salarisgroep"].isin(_pick)]
            st.dataframe(_shown[["Name", "Matched role", "Function", "Level", "Grade",
                                 "Functiegroep", "Salarisgroep"]],
                        use_container_width=True, hide_index=True)
            st.caption(f"Label alignment only, {_sector} — CATS® has no public point-range table to "
                       "position against (unlike ISF). Official classification requires reading the "
                       "sector's niveaublad for the relevant functiefamilie, done by a certified CATS® user.")

        # Supporting context (never an input to a scoring formula): job description +
        # skill class/family, so a reviewer can sanity-check the indicative position.
        _roles = sorted(graded["Matched role"].dropna().unique())
        if _roles:
            with st.expander("Inspect a role — description & skill family (context, not a score input)"):
                _role_pick = st.selectbox("Role", _roles, key="cao_crosswalk_inspect_role")
                _rowmatch = graded[graded["Matched role"] == _role_pick].iloc[0]
                st.markdown(f"**{_role_pick}** · Function {_rowmatch.get('Function','—')} · "
                           f"Level {_rowmatch.get('Level','—')} · Grade {_rowmatch.get('Grade','—')}")
                _desc = _rowmatch.get("Description") or ""
                st.write(_desc if _desc else "_No description on file for this role._")
                _jid = _rowmatch.get("JobId")
                _reqs = repo.role_skill_map.get(_jid, []) if _jid else []
                if _reqs:
                    _skilltbl = _pd.DataFrame([{
                        "Skill": repo.skills[req.skill_id].skill_name if req.skill_id in repo.skills else req.skill_id,
                        "Class (family)": repo.skills[req.skill_id].category if req.skill_id in repo.skills else "—",
                        "Required level": req.required_level, "Type": req.skill_type,
                    } for req in _reqs])
                    st.dataframe(_skilltbl, use_container_width=True, hide_index=True)
                else:
                    st.caption("No skill requirements on file for this role.")

    # ── gender pay gap & equity reasoning (EU Pay Transparency Directive) ──
    if gender_col and "Gender" in priced.columns:
        gm = priced[priced["Gender"] == "M"]; gf = priced[priced["Gender"] == "F"]
        n_x = int((~priced["Gender"].isin(["M", "F"])).sum())
        if len(gm) and len(gf):
            _basis = "Actual FT" if "Actual FT" in priced.columns else "Actual"
            _fte_on = bool(fte_col)

            def _gap(a, b):
                return round((a - b) / a * 100, 1) if a else None

            def _c(v):
                return C["danger"] if (v is not None and abs(v) >= 5) else C["teal"]

            raw_mean = _gap(gm[_basis].mean(), gf[_basis].mean())
            raw_med = _gap(gm[_basis].median(), gf[_basis].median())
            compa_gap = round((gm["Compa-ratio"].mean() - gf["Compa-ratio"].mean()) * 100, 1)
            _xnote = f", X/other n={n_x} excluded" if n_x else ""
            st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                        f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">'
                        f'Gender pay gap &amp; equity reasoning</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div style="font-size:14px;color:{C["ink"]}">'
                f'Mean gap (M vs F): <b style="color:{_c(raw_mean)}">{raw_mean:+.1f}%</b> &nbsp;·&nbsp; '
                f'Median gap: <b style="color:{_c(raw_med)}">{raw_med:+.1f}%</b> &nbsp;·&nbsp; '
                f'Compa-ratio gap: <b>{compa_gap:+.1f} pts</b> &nbsp;'
                f'<span style="color:{C["muted"]}">(M n={len(gm)}, F n={len(gf)}{_xnote})</span></div>',
                unsafe_allow_html=True)
            st.caption("Positive = men paid more. Mean and median are both shown, as the Directive requires "
                       "(median is less distorted by a few high earners). " +
                       ("Salaries are compared full-time-equivalent (base ÷ FTE)." if _fte_on else
                        "⚠ No FTE column supplied — part-time pay is NOT normalised; in the Dutch context "
                        "(high, strongly gendered part-time rates) this tends to overstate the gap."))
            # total-pay gap (mean + median) + who actually receives variable pay
            if has_variable:
                _tb = ("Total pay FT" if "Total pay FT" in priced.columns
                       else ("Total pay" if "Total pay" in priced.columns else None))
                if _tb:
                    tp_mean = _gap(gm[_tb].mean(), gf[_tb].mean())
                    tp_med = _gap(gm[_tb].median(), gf[_tb].median())
                    _d = (tp_mean - raw_mean) if (tp_mean is not None and raw_mean is not None) else 0.0
                    _w = "widens" if _d > 0 else "narrows" if _d < 0 else "does not change"
                    st.markdown(
                        f'<div style="font-size:14px;color:{C["ink"]};margin-top:4px">'
                        f'Total-pay gap (base + bonus + allowances + LTI): '
                        f'mean <b style="color:{_c(tp_mean)}">{tp_mean:+.1f}%</b> &nbsp;·&nbsp; '
                        f'median <b style="color:{_c(tp_med)}">{tp_med:+.1f}%</b> &nbsp;'
                        f'<span style="color:{C["muted"]}">({_d:+.1f} pts vs base — variable pay {_w} the gap)</span>'
                        f'</div>', unsafe_allow_html=True)
                # Isolated variable-pay gap (Bonus+Allowances+LTI alone, not folded into
                # total pay) -- the Directive requires this as its OWN reported metric,
                # separate from the base gap and the combined total-pay gap above.
                _varamt_col = "_var_amt"
                priced[_varamt_col] = priced["Bonus"].fillna(0) + priced["Allowances"].fillna(0) + priced["LTI"].fillna(0)
                vp_mean = _gap(gm[_varamt_col].mean(), gf[_varamt_col].mean())
                vp_med = _gap(gm[_varamt_col].median(), gf[_varamt_col].median())
                if vp_mean is not None:
                    st.markdown(
                        f'<div style="font-size:14px;color:{C["ink"]};margin-top:4px">'
                        f'Variable-pay gap (bonus + allowances + LTI only): '
                        f'mean <b style="color:{_c(vp_mean)}">{vp_mean:+.1f}%</b> &nbsp;·&nbsp; '
                        f'median <b style="color:{_c(vp_med)}">{vp_med:+.1f}%</b></div>', unsafe_allow_html=True)
                    st.caption("Reported on the variable amounts themselves (zero for anyone who receives none), "
                               "as its own figure — the Directive requires this separately from the base and "
                               "total-pay gaps above, since a gap can hide entirely inside who gets a bonus and how much.")
                _var = (priced["Bonus"].fillna(0) + priced["Allowances"].fillna(0) + priced["LTI"].fillna(0)) > 0
                pm = round(100 * _var[priced["Gender"] == "M"].mean()) if len(gm) else 0
                pf = round(100 * _var[priced["Gender"] == "F"].mean()) if len(gf) else 0
                st.caption(f"Receiving any variable pay — men {pm}% · women {pf}% "
                           "(the Directive also reports who receives variable components, not only their size).")

            # per-category gaps — the 5% trigger is per category of equal / equal-value work, not org-wide
            SMALL_N = 5
            def _cat_gaps(keycol, label):
                out = []
                for key, grp in priced.groupby(keycol):
                    a = grp[grp["Gender"] == "M"]; b = grp[grp["Gender"] == "F"]
                    if len(a) and len(b):
                        g = _gap(a[_basis].mean(), b[_basis].mean())
                        out.append({label: key, "M": len(a), "F": len(b),
                                    "M mean": round(a[_basis].mean()), "F mean": round(b[_basis].mean()),
                                    "Gap %": g, "≥5%?": "⚠ yes" if (g is not None and abs(g) >= 5) else "no",
                                    "Sample": "low n" if min(len(a), len(b)) < SMALL_N else "ok"})
                return out

            role_gaps = _cat_gaps("Matched role", "Role (equal work)")
            grade_gaps = (_cat_gaps("Grade", "Grade (equal value)")
                          if "Grade" in priced.columns and priced["Grade"].notna().any() else [])
            _flagged = [x for x in role_gaps if str(x["≥5%?"]).startswith("⚠")]
            n_breach = len(_flagged)
            n_breach_robust = sum(1 for x in _flagged if x["Sample"] == "ok")

            _reason = [f"Overall median gap {raw_med:+.1f}% (mean {raw_mean:+.1f}%)."]
            if role_gaps:
                _bcol = C["danger"] if n_breach else C["teal"]
                _rob = (f" ({n_breach_robust} with a reliable sample of ≥{SMALL_N} per gender, "
                        f"the rest small-sample)" if n_breach else "")
                _reason.append(f'<b style="color:{_bcol}">{n_breach} of {len(role_gaps)}</b> role categories '
                               f'(with both men and women) show a gap of 5% or more{_rob}.')
            else:
                _reason.append("No role category has both men and women yet — add more rows for category-level testing.")
            _reason.append('Under the Directive a gap of ≥5% <b>within a category of equal or equal-value work</b> '
                           'triggers a <b>joint pay assessment</b> — but only if it is <b>not justified</b> by '
                           'objective, gender-neutral criteria and <b>not remedied within 6 months</b>. '
                           'A high org-wide gap on its own is context, not a breach.')
            _reason.append('<b>These gaps are unadjusted</b> — not controlled for tenure, performance, location or '
                           'working hours, and small categories are noisy. Treat a flag as a prompt to investigate '
                           'that category, not proof of an unjustified gap.')
            _reason.append('Role and Grade are used here as the “equal work” / “equal value” '
                           'groupings. The Directive (Art. 4) requires these groupings to come from a '
                           '<b>gender-neutral job evaluation and classification system</b> — built on skills, '
                           'effort, responsibility and working conditions. This tool does not verify that the '
                           'client’s own role/grade structure meets that standard; if the structure itself '
                           'carries bias, a gap analysis on top of it can understate the true picture. (The '
                           'Structural gender pay gap mode on Function×Level runs a statistical grade-assignment '
                           'check for this — worth using alongside this compa-ratio view.)')
            _rcol = C["danger"] if n_breach else C["teal"]
            st.markdown(
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                f'border-left:3px solid {_rcol};border-radius:10px;padding:13px 15px;margin:12px 0;'
                f'font-size:13.5px;color:{C["ink"]};line-height:1.55">'
                f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
                f'color:{C["muted"]};margin-bottom:6px">Equity reasoning</div>' + " ".join(_reason) + '</div>',
                unsafe_allow_html=True)

            if role_gaps:
                with st.expander(f"Per-role gap — equal work ({len(role_gaps)} categories with M and F)"):
                    st.dataframe(_pd.DataFrame(role_gaps), use_container_width=True, hide_index=True)
            if grade_gaps:
                with st.expander(f"Per-grade gap — equal value ({len(grade_gaps)} grades with M and F)"):
                    st.caption("Groups different roles of the same grade — approximates 'work of equal value'.")
                    st.dataframe(_pd.DataFrame(grade_gaps), use_container_width=True, hide_index=True)

            # pay quartiles by gender (Directive Art. 9 reporting metric)
            try:
                _q = _pd.qcut(priced[_basis], 4, labels=["Q1 lowest", "Q2", "Q3", "Q4 highest"], duplicates="drop")
                _qt = _pd.crosstab(_q, priced["Gender"])
                for _g in ("M", "F"):
                    if _g not in _qt.columns:
                        _qt[_g] = 0
                _tot = _qt.sum(axis=1)
                _qt["% women"] = (100 * _qt["F"] / _tot).fillna(0).round().astype(int)
                with st.expander("Gender split across pay quartiles"):
                    st.caption("The Directive reports the share of women and men in each quartile pay band. "
                               "Few women in Q4 (or many in Q1) points to vertical segregation behind the gap.")
                    st.dataframe(_qt.reset_index().rename(columns={_basis: "Quartile"}),
                                 use_container_width=True, hide_index=True)
            except Exception:
                pass
        else:
            st.info(f"A Gender column is present, but the gap needs both men and women with matched pay "
                    f"(currently men n={len(gm)}, women n={len(gf)}). Add the missing group to compute the gender gap.")
    else:
        st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">'
                    f'Gender pay gap &amp; equity reasoning</div>', unsafe_allow_html=True)
        st.info("➕ Add a **Gender** column (M / F — Dutch M / V is read natively) to unlock the gender pay-gap analysis — mean & median "
                "gaps on base and total pay, per-category testing against the 5% threshold, the pay-quartile "
                "split and variable-pay coverage.")

    # ── workforce cost & remediation scenario (#4) ──────────────────────
    if len(priced):
        # Every rate in this figure comes from PayElements and PayMix through one
        # service. It used to be written out here as literals -- 8% holiday,
        # 12% pension, EUR 2.000 of benefits -- two of which the library
        # contradicts: pension is stated as a range, and benefits as "varies".
        from services import pay_components_service as _pay
        _repo = catalog.repository
        base_bill = float(priced["Actual"].sum())
        reward_low = reward_high = 0.0
        _no_mix = 0
        _excluded_labels: set = set()
        for _, pr in priced.iterrows():
            _comp = _pay.compose(float(pr["Actual"]), pr.get("Function", ""),
                                 pr.get("Level", ""), _repo)
            reward_low += _comp.total_reward_low
            reward_high += _comp.total_reward_high
            if any(c.key == "variable" for c in _comp.excluded):
                _no_mix += 1
            _excluded_labels |= {c.label.lower() for c in _comp.excluded}
        rem_min = float(sum(max(0.0, float(pr["Band min"]) - float(pr["Actual"])) for _, pr in priced.iterrows()))
        rem_p50 = float(sum(max(0.0, float(pr["Band P50"]) - float(pr["Actual"])) for _, pr in priced.iterrows()))
        n_below = int((priced["Actual"] < priced["Band min"]).sum())
        _e = _money
        st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">Workforce cost & remediation</div>',
                    unsafe_allow_html=True)
        _reward_text = (_e(reward_low) if round(reward_low) == round(reward_high)
                        else f"{_e(reward_low)} – {_e(reward_high)}")
        ctiles = [("Base paybill", _e(base_bill), C["ink"]),
                  ("Est. total reward", _reward_text, C["teal"]),
                  (f"Fix below-range ({n_below})", _e(rem_min), C["danger"] if rem_min else C["ink"]),
                  ("Bring all to market P50", _e(rem_p50), C["amber"] if rem_p50 else C["ink"])]
        crow = "".join(
            f'<div style="flex:1;min-width:150px;background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-radius:12px;padding:14px 16px"><div style="font-family:{FONT_SERIF};font-size:22px;'
            f'font-weight:700;color:{col}">{val}</div><div style="font-family:{FONT_MONO};font-size:10px;'
            f'letter-spacing:.06em;text-transform:uppercase;color:{C["muted"]};margin-top:2px">{lab}</div></div>'
            for lab, val, col in ctiles)
        st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap">{crow}</div>', unsafe_allow_html=True)
        _caption = ("Total reward is built from the library: holiday allowance and employer "
                    "pension from PayElements, 13th month and on-target variable from PayMix "
                    "per Function × Level. Pension is stated there as a range, so this is a "
                    "range and not a single figure.")
        if _excluded_labels:
            _caption += (" Left out because the library states no rate for them: "
                         + ", ".join(sorted(_excluded_labels)) + ".")
        if _no_mix:
            _caption += (f" {_no_mix} of {len(priced)} employees sit in a Function × Level with "
                         f"no PayMix row, so their variable entitlement is unknown rather than zero "
                         f"and is not in this figure.")
        _caption += (" 'Fix below-range' is the annual base cost to lift underpaid staff to their "
                     "band minimum; 'to market P50' brings everyone below the midpoint up to it.")
        st.caption(_caption)

    # ── table + export ──────────────────────────────────────────────────
    def _row_style(row):
        c = STATUS_COLOR.get(row["Status"], "#8A93A5")
        return [f"color:{c};font-weight:600" if col == "Status" else "" for col in row.index]
    show_cols = [c for c in ["Name", "Input title", "Matched role", "Level", "FTE", "Actual", "Actual FT",
                             "Total cash", "Total pay", "Total pay FT", "Band P50", "Range %", "Compa-ratio", "Status"]
                 if c in res.columns]
    st.dataframe(res[show_cols].style.apply(_row_style, axis=1), use_container_width=True, hide_index=True)
    _xb = _io.BytesIO(); res.to_excel(_xb, index=False)
    _logged_download("⬇ Download pay-equity analysis (.xlsx)", _xb.getvalue(),
        file_name="jobsy_pay_equity.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

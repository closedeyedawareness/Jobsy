"""ui/views/skills_dashboard.py — moved verbatim out of ui/app.py on 2026-09-03."""

from __future__ import annotations

from ui.shared import *  # noqa: F401,F403


def skills_dashboard_page(catalog):
    """Skills-based organisation lens: org-wide skills intelligence (tiles +
    category treemap + demand/supply table) and the per-role proficiency wheel.
    Demand side = the reference library; supply side = assessments uploaded on
    the Skills Assessment page (session), honestly labelled by source."""
    import pandas as _pd
    try:
        from services.skills_dashboard_service import (
            build_wheel_svg, overlay_supply, skill_demand, squarify)
    except ImportError:
        from jobsy.services.skills_dashboard_service import (
            build_wheel_svg, overlay_supply, skill_demand, squarify)

    repo = catalog.repository
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Skills Dashboard</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'The organisation seen through <b>what people can do</b> rather than where they sit '
        f'in a hierarchy. Demand side comes from the role architecture ({len(repo.jobs)} roles); '
        f'supply side appears when assessments are uploaded on the Skills Assessment page.</p>',
        unsafe_allow_html=True,
    )

    # supply: session assessments {emp: {skill_id: level}} -> flat shim list
    _sa = st.session_state.get("skill_assessments") or {}

    class _A:  # noqa: N801 - tiny adapter
        __slots__ = ("skill_id", "current_level")
        def __init__(self, sid, lvl):
            self.skill_id, self.current_level = sid, lvl

    flat = [_A(sid, lvl) for skills in _sa.values() for sid, lvl in skills.items() if lvl and lvl > 0]
    demand = overlay_supply(skill_demand(repo), flat)

    # ── headline tiles ──────────────────────────────────────────────────
    n_cats = len({s.category for s in demand})
    tiles = [("Skill categories", str(n_cats), C["ink"]),
             ("Skills in demand", str(len(demand)), C["violet"]),
             ("Roles architected", str(len(repo.jobs)), C["teal"]),
             ("People assessed", str(len(_sa)) if _sa else "—", C["accent"] if _sa else C["muted"])]
    trow = "".join(
        f'<div style="flex:1;min-width:120px;background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-radius:12px;padding:14px 16px"><div style="font-family:{FONT_SERIF};font-size:28px;'
        f'font-weight:700;color:{col}">{val}</div><div style="font-family:{FONT_MONO};font-size:10px;'
        f'letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]};margin-top:2px">{lab}</div></div>'
        for lab, val, col in tiles)
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 16px">{trow}</div>',
                unsafe_allow_html=True)
    if not _sa:
        st.caption("➕ Upload assessments on the **Skills Assessment** page to light up the supply side "
                   "(holders per skill, held-vs-required overlay on the wheel). Declared ≠ validated — "
                   "the source of each assessment matters and is carried through.")

    # ── declared skills — from your file, by department ─────────────────
    if _sa:
        try:
            from services.skills_dashboard_service import declared_skills_heatmap
        except ImportError:
            from jobsy.services.skills_dashboard_service import declared_skills_heatmap
        _emp_dept = st.session_state.get("skill_assessment_departments") or {}
        _hm = declared_skills_heatmap(_sa, _emp_dept, repo)
        st.markdown(
            f'<div style="display:inline-block;font-family:{FONT_MONO};font-size:10px;'
            f'letter-spacing:.1em;text-transform:uppercase;color:{C["accent"]};'
            f'border:1px solid {C["accent"]};border-radius:999px;padding:3px 10px;margin:18px 0 10px">'
            f'● Declared skills · from your file</div>', unsafe_allow_html=True)
        if not _emp_dept:
            st.caption("No Department column recognised on the assessment upload — everyone is grouped "
                       "under **Unassigned**. Re-upload with a Department/Team column to split this by team.")
        _depts = _hm.departments
        _maxpct = 1.0
        _rows_html = []
        for row in _hm.rows:
            cells = "".join(
                (lambda p: f'<div style="text-align:center;font-family:{FONT_MONO};font-size:11px;'
                          f'font-weight:700;border-radius:8px;padding:6px 2px;'
                          f'background:rgba(111,60,255,{0.06 + 0.85*(p/100):.3f});'
                          f'color:{C["ink"] if p >= 25 else C["muted"]}">'
                          f'{f"{p:.0f}%" if p > 0 else "·"}</div>')(row.by_department.get(d, 0.0))
                for d, _ in _depts)
            _rows_html.append(
                f'<div style="display:grid;grid-template-columns:180px repeat({len(_depts)},1fr);'
                f'gap:4px;align-items:center;padding:2px 0">'
                f'<div style="font-size:12.5px;color:{C["ink"]}">{row.skill_name}'
                f'<div style="font-family:{FONT_MONO};font-size:9.5px;color:{C["muted"]}">'
                f'{row.total_holders} hold</div></div>{cells}</div>')
        _header = (f'<div style="display:grid;grid-template-columns:180px repeat({len(_depts)},1fr);'
                  f'gap:4px;margin-bottom:6px">' + '<div></div>' +
                  ''.join(f'<div style="text-align:center;font-family:{FONT_MONO};font-size:10px;'
                          f'letter-spacing:.04em;text-transform:uppercase;color:{C["muted"]}">{d}'
                          f'<div style="font-weight:700;color:{C["ink"]};font-size:12px">{n}</div></div>'
                          for d, n in _depts) + '</div>')
        if _hm.rows:
            st.markdown(f'<div style="overflow-x:auto">{_header}{"".join(_rows_html)}</div>',
                       unsafe_allow_html=True)
            st.caption("Each team's own top **declared** skills — cell = share of that team who declared it. "
                       "Self-reported, not validated: pair with the Skills Assessment page's confidence "
                       "levels before treating a gap as real.")
        else:
            st.caption("No declared skills to show yet.")

    # ── category treemap ───────────────────────────────────────────────
    _sizelab = ("people holding (assessments)" if _sa else "requirement instances (role × skill)")
    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:14px 0 6px">'
                f'Skills map — size = {_sizelab}</div>', unsafe_allow_html=True)
    cats = sorted({s.category for s in demand})
    cat_pick = st.selectbox("Category", ["All categories"] + cats, key="sd_cat")
    subset = demand if cat_pick == "All categories" else [s for s in demand if s.category == cat_pick]
    if cat_pick == "All categories":
        items = []
        for c in cats:
            v = sum((s.n_holders if _sa else s.n_roles) for s in demand if s.category == c)
            items.append((c, float(v)))
    else:
        items = [(s.skill_name, float(s.n_holders if _sa else s.n_roles)) for s in subset]
    rects = squarify(items, 0, 0, 100, 56)
    _PALETTE = ["#A87CFF", "#8850EF", "#67E8F9", "#F472B6", "#6EE7B7", "#4d2c80", "#3a2064", "#271052"]  # pillars first, then the PH panel ramp
    cells = []
    for i, r in enumerate(sorted(rects, key=lambda r: -(r.w * r.h))):
        fs = max(9, min(15, (r.w * r.h) ** 0.5 * 0.55))
        cells.append(
            f'<div style="position:absolute;left:{r.x}%;top:{r.y / 56 * 100}%;width:{r.w}%;'
            f'height:{r.h / 56 * 100}%;background:{_PALETTE[i % len(_PALETTE)]};'
            f'border:1px solid {C["bg"]};border-radius:4px;overflow:hidden;display:flex;'
            f'align-items:center;justify-content:center;text-align:center;padding:2px">'
            f'<span style="font-size:{fs:.0f}px;color:#FFFFFF;line-height:1.15">{r.label}'
            f'<br><span style="opacity:.75;font-size:{fs*0.85:.0f}px">{r.value:.0f}</span></span></div>')
    st.markdown(f'<div style="position:relative;width:100%;aspect-ratio:100/56;'
                f'background:{C["surface"]};border-radius:10px;margin-bottom:14px">{"".join(cells)}</div>',
                unsafe_allow_html=True)

    # ── demand / supply table ──────────────────────────────────────────
    with st.expander(f"Skills table ({len(subset)} in view)"):
        st.caption("Demand = the role architecture (roles requiring, Core count, max required level). "
                   "Supply = uploaded assessments; blank until they exist rather than pretending.")
        tbl = _pd.DataFrame([{
            "Skill": s.skill_name, "Category": s.category, "Roles requiring": s.n_roles,
            "Core in": s.n_core, "Max req. level": s.max_required_level,
            "Holders": (s.n_holders if _sa else None), "Avg level held": s.avg_level_held,
        } for s in sorted(subset, key=lambda s: -(s.n_holders if _sa else s.n_roles))])
        st.dataframe(tbl, use_container_width=True, hide_index=True)

    # ── proficiency wheel ──────────────────────────────────────────────
    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">'
                f'Proficiency wheel — required profile per role</div>', unsafe_allow_html=True)
    titles = sorted(j.standard_title for j in repo.jobs.values() if repo.role_skill_map.get(j.job_id))
    role_pick = st.selectbox("Role", titles, key="sd_role")
    job = next(j for j in repo.jobs.values() if j.standard_title == role_pick)
    reqs = [{"skill": (repo.skills[r.skill_id].skill_name if r.skill_id in repo.skills else r.skill_id),
             "level": r.required_level, "type": r.skill_type}
            for r in sorted(repo.role_skill_map.get(job.job_id, []),
                            key=lambda r: (-r.required_level, r.skill_type))]

    overlay = None
    emp_pick = None
    if _sa:
        emp_pick = st.selectbox("Overlay a person (from uploaded assessments)",
                                ["— none —"] + sorted(_sa.keys()), key="sd_emp")
        if emp_pick and emp_pick != "— none —":
            _name_by_id = {sid: (repo.skills[sid].skill_name if sid in repo.skills else sid)
                           for sid in _sa[emp_pick]}
            overlay = {_name_by_id[sid]: lvl for sid, lvl in _sa[emp_pick].items() if lvl and lvl > 0}

    st.markdown(f'<div style="max-width:660px;margin:0 auto">'
                f'{build_wheel_svg(role_pick, reqs, overlay_levels=overlay)}</div>',
                unsafe_allow_html=True)
    _legend = (f'<span style="color:{C["violet"]}">■</span> required level (rings 1–5) &nbsp; '
               f'<b style="font-size:12px">bold</b> = Core skill')
    if overlay:
        _legend += f' &nbsp; <span style="color:{C["accent"]}">■</span> {emp_pick} — current level'
    st.caption(_legend, unsafe_allow_html=True)
    st.caption("Skill-based structure in one picture: the role is its required capability profile, "
               "not a box on an org chart. Overlay a person to see fit and growth edges — gaps are "
               "development conversations, not verdicts.")

    # ── departmental overlap — the mobility corridors ──────────────────
    try:
        from services.skills_dashboard_service import function_overlaps, future_skill_readiness
    except ImportError:
        from jobsy.services.skills_dashboard_service import function_overlaps, future_skill_readiness

    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:22px 0 6px">'
                f'Departmental overlap — shared skills between functions</div>', unsafe_allow_html=True)
    st.caption("Where departments already speak each other's language. High overlap = an internal "
               "mobility corridor: people can cross on capabilities they demonstrably share. "
               "Similarity is cosine on level-weighted skill profiles; 'shared' counts distinct skills.")
    overlaps = function_overlaps(repo)
    if overlaps:
        _otbl = _pd.DataFrame([{
            "Function A": o.function_a, "Function B": o.function_b,
            "Similarity": o.cosine, "Shared skills": len(o.shared_skills),
            "Top shared": ", ".join(o.shared_skills[:3]) + ("…" if len(o.shared_skills) > 3 else ""),
        } for o in overlaps])
        st.dataframe(_otbl, use_container_width=True, hide_index=True,
                     column_config={"Similarity": st.column_config.ProgressColumn(
                         "Similarity", min_value=0.0, max_value=1.0, format="%.2f")})
        _pairs = [f"{o.function_a} ↔ {o.function_b}" for o in overlaps]
        with st.expander("Inspect a corridor — every skill two functions share"):
            _pk = st.selectbox("Function pair", _pairs, key="sd_overlap_pair")
            _o = overlaps[_pairs.index(_pk)]
            if _o.shared_skills:
                st.markdown(" · ".join(f"`{s}`" for s in _o.shared_skills))
                st.caption(f"Jaccard {_o.jaccard:.2f} — these functions share "
                           f"{len(_o.shared_skills)} of their combined distinct skills. Each shared "
                           "skill is a bridge a person can cross without starting over.")
            else:
                st.caption("No shared skills — these functions currently have no direct corridor.")

        # full symmetric matrix + redeployment-lane narrative, same overlap
        # math as the table above, read at a glance instead of row by row.
        try:
            from services.skills_dashboard_service import redeployment_summary
        except ImportError:
            from jobsy.services.skills_dashboard_service import redeployment_summary
        _rs = redeployment_summary(repo)
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.1em;'
            f'text-transform:uppercase;color:{C["muted"]};margin:18px 0 8px">'
            f'Shared-capability index · department × department</div>', unsafe_allow_html=True)
        _fns = _rs.functions
        _mcol1, _mcol2 = st.columns([1.6, 1])
        with _mcol1:
            _mheader = ('<div style="display:grid;grid-template-columns:120px '
                       f'repeat({len(_fns)},1fr);gap:3px;margin-bottom:3px">' + '<div></div>' +
                       ''.join(f'<div style="text-align:center;font-family:{FONT_MONO};font-size:9px;'
                               f'color:{C["muted"]};writing-mode:vertical-rl;transform:rotate(180deg);'
                               f'height:70px;padding-bottom:3px">{f}</div>' for f in _fns) + '</div>')
            _mrows = []
            _maxv = max([v for v in _rs.matrix.values()] or [1.0])
            for a in _fns:
                cells = []
                for b in _fns:
                    if a == b:
                        cells.append(f'<div style="border-radius:6px;background:repeating-linear-gradient('
                                     f'45deg,{C["line"]},{C["line"]} 3px,transparent 3px,transparent 6px);'
                                     f'min-height:26px"></div>')
                    else:
                        v = _rs.matrix.get((a, b), 0.0)
                        inten = min(1.0, v / _maxv) if _maxv else 0
                        cells.append(
                            f'<div style="text-align:center;font-family:{FONT_MONO};font-size:10.5px;'
                            f'font-weight:700;border-radius:6px;padding:5px 2px;min-height:16px;'
                            f'background:rgba(111,60,255,{0.05 + 0.85*inten:.3f});'
                            f'color:{C["ink"] if inten >= 0.25 else C["muted"]}">'
                            f'{f"{100*v:.0f}" if v > 0 else "·"}</div>')
                _mrows.append(
                    f'<div style="display:grid;grid-template-columns:120px repeat({len(_fns)},1fr);'
                    f'gap:3px;align-items:center;margin:2px 0">'
                    f'<div style="font-size:11.5px;color:{C["ink"]};text-align:right;padding-right:6px">{a}</div>'
                    + ''.join(cells) + '</div>')
            st.markdown(f'<div style="overflow-x:auto">{_mheader}{"".join(_mrows)}</div>',
                       unsafe_allow_html=True)
            st.caption("Shared capability % (skill-profile similarity) — higher = more overlap. "
                       "▨ = same department (excluded, not zero).")
        with _mcol2:
            st.markdown(f'<div style="font-family:{FONT_MONO};font-size:10.5px;letter-spacing:.08em;'
                        f'text-transform:uppercase;color:{C["teal"]};margin-bottom:6px">'
                        f'Strongest redeployment lanes</div>', unsafe_allow_html=True)
            for i, lane in enumerate(_rs.top_lanes, 1):
                _skill_note = (f"Shared strength in <b>{lane.top_skill}</b> — cover and redeployment are "
                               f"low-friction." if lane.top_skill else
                               "A shared-skill base makes cover between them straightforward.")
                st.markdown(
                    f'<div style="margin-bottom:10px"><span style="font-family:{FONT_SERIF};'
                    f'font-weight:700;color:{C["violet"]};margin-right:6px">{i}</span>'
                    f'<b style="color:{C["ink"]}">{lane.a} ↔ {lane.b}</b>'
                    f'<div style="font-size:12px;color:{C["muted"]};margin-top:2px">{_skill_note}</div></div>',
                    unsafe_allow_html=True)
            if _rs.most_isolated:
                st.markdown(
                    f'<div style="margin-top:10px;padding:10px 12px;border-radius:10px;'
                    f'background:{C["surface"]};border:1px solid {C["danger"]}"> '
                    f'<b style="color:{C["danger"]}">! {_rs.most_isolated} is the most isolated</b>'
                    f'<div style="font-size:12px;color:{C["muted"]};margin-top:3px">It shares the least '
                    f'capability with the rest of the business — its specialist skills have no natural '
                    f'backup. Cross-train a second holder for each.</div></div>', unsafe_allow_html=True)

    # ── skills of the future — sourced overlay vs the org ──────────────
    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:22px 0 6px">'
                f'Skills of the future — what the organisation still misses</div>', unsafe_allow_html=True)
    st.caption("Analytical overlay, not measurement: future-skill demand from sourced research "
               "(WEF Future of Jobs 2025 · LinkedIn Skills on the Rise 2025), matched to this "
               "organisation's own skill catalogue by visible keyword rules — check the match, "
               "don't take it on faith.")
    _future = future_skill_readiness(repo, assessments=flat)
    _fs_color = {"Not in catalogue": C["danger"], "Missing": C["danger"],
                 "Emerging": C["amber"], "Covered": C["teal"]}
    _gaps = [f for f in _future if f.status in ("Not in catalogue", "Missing")]
    if _gaps:
        st.markdown(
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-left:3px solid {C["danger"]};border-radius:10px;padding:12px 14px;margin:8px 0;'
            f'font-size:13.5px;color:{C["ink"]}"><b style="color:{C["danger"]}">Still missing:</b> ' +
            " · ".join(f"<b>{f.name}</b> <span style=\"color:{C['muted']}\">({f.source})</span>" for f in _gaps) +
            '<br><span style="color:' + C["muted"] + ';font-size:12.5px">"Not in catalogue" is the deeper gap: '
            'the taxonomy cannot even see the skill yet — adding it to the catalogue is step one, '
            'requiring it in roles is step two.</span></div>', unsafe_allow_html=True)
    _cards = "".join(
        f'<div style="flex:1;min-width:230px;background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-left:3px solid {_fs_color[f.status]};border-radius:12px;padding:12px 14px">'
        f'<div style="font-size:.92rem;font-weight:600;color:{C["ink"]}">{f.name}</div>'
        f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.06em;text-transform:uppercase;'
        f'color:{C["muted"]};margin:2px 0 6px">{f.source}</div>'
        f'<div style="font-size:.8rem;color:{_fs_color[f.status]};font-weight:700">{f.status}</div>'
        f'<div style="font-size:.78rem;color:{C["muted"]};margin-top:4px">'
        + (f'{f.n_roles_requiring} roles require · ' if f.n_roles_requiring else '')
        + (f'{f.n_holders} people hold · ' if f.n_holders else '')
        + (f'matches: {", ".join(f.matched_skills[:2])}{"…" if len(f.matched_skills) > 2 else ""}'
           if f.matched_skills else 'no catalogue match') + '</div></div>'
        for f in _future)
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 16px">{_cards}</div>',
                unsafe_allow_html=True)
    with st.expander("Full match table — how each future skill maps to the catalogue"):
        st.dataframe(_pd.DataFrame([{
            "Future skill": f.name, "Source": f.source, "Status": f.status,
            "Roles requiring": f.n_roles_requiring, "People holding": (f.n_holders or None),
            "Catalogue matches": ", ".join(f.matched_skills) or "—",
        } for f in _future]), use_container_width=True, hide_index=True)

"""ui/pages/org_hierarchy.py — moved verbatim out of ui/app.py on 2026-09-03."""

from __future__ import annotations

from ui.shared import *  # noqa: F401,F403


def org_hierarchy_page(catalog):
    """Render the automatic organisation hierarchy from matched results."""
    LEVEL_ORDER_MAP  = {"Junior": 1, "Medior": 2, "Senior": 3, "Lead": 4}
    LEVEL_BADGE_COL  = {
        "Lead":   (C["violet"], C["violet"]+"1A"),
        "Senior": (C["teal"],   C["teal"]+"1A"),
        "Medior": (C["blue"],   C["blue"]+"1A"),
        "Junior": (C["amber"],  C["amber"]+"1A"),
    }

    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Organisation Hierarchy</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:20px">'
        f'Automatically structured by function and seniority grade from matched titles.</p>',
        unsafe_allow_html=True,
    )

    results  = st.session_state.get("last_results", [])
    df_input = st.session_state.get("upload_df")
    name_col = st.session_state.get("upload_name_col")
    title_col = st.session_state.get("upload_title_col")

    if not results:
        st.info("Run a match on the Matching page first — upload a file with employee titles to build the hierarchy.")
        return

    matched = [r for r in results if r.matched]
    if not matched:
        st.warning("No titles could be matched. Check the reference workbook is selected.")
        return

    # build name lookup — handle both single name col and FirstName/LastName split
    names = {}
    if df_input is not None:
        has_split = "FirstName" in df_input.columns and "LastName" in df_input.columns
        for idx, row in df_input.iterrows():
            if idx >= len(results):
                break
            if has_split:
                fn_v = str(row.get("FirstName","")).strip()
                ln_v = str(row.get("LastName","")).strip()
                full = (fn_v + " " + ln_v).strip()
                names[idx] = full if full else None
            elif name_col and name_col != "— none —":
                names[idx] = str(row.get(name_col,"")).strip() or None

    # detect dept column from uploaded df
    dept_col = None
    if df_input is not None:
        for candidate in ["Department","department","Dept","dept","BusinessUnit","business_unit","Function"]:
            if candidate in df_input.columns:
                dept_col = candidate
                break

    # group by department (from upload) or matched function → level
    from collections import defaultdict
    tree = defaultdict(lambda: defaultdict(list))
    for idx, r in enumerate(results):
        if not r.matched:
            continue
        # prefer uploaded department column for grouping
        if dept_col and df_input is not None and idx < len(df_input):
            fn = str(df_input.iloc[idx][dept_col]).strip() or r.function or "Other"
        else:
            fn = r.function or "Other"
        lv  = r.level    or "Medior"
        person_name = names.get(idx)
        # next step
        next_role = ""
        try:
            cp = catalog.repository.career_paths.get(r.job_id)
            if cp and cp.next_job_id:
                nj = catalog.repository.jobs.get(cp.next_job_id)
                if nj:
                    next_role = nj.standard_title
        except Exception:
            pass
        tree[fn][lv].append({
            "name":       person_name,
            "title":      r.input_title,
            "std_title":  r.standard_title,
            "confidence": r.confidence,
            "match_type": r.match_type.value,
            "next_role":  next_role,
            "job_id":     r.job_id,
        })

    # summary stats
    total   = sum(len(v) for fn in tree for v in tree[fn].values())
    n_fns   = len(tree)
    n_lead  = sum(len(tree[fn].get("Lead",[])) for fn in tree)
    n_junior = sum(len(tree[fn].get("Junior",[])) for fn in tree)
    st.markdown(
        f'<div style="display:flex;gap:10px;margin:0 0 20px">'
        f'{_stat_card(total,"Employees")}{_stat_card(n_fns,"Departments")}'
        f'{_stat_card(n_lead,"Lead roles",C["violet"])}{_stat_card(n_junior,"Junior roles",C["amber"])}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # render each function block
    fn_order = sorted(tree.keys(), key=lambda f: f)
    level_order = ["Lead","Senior","Medior","Junior"]
    cat_map = {j.function: j for j in catalog.repository.jobs.values()}

    for fn in fn_order:
        fn_levels = tree[fn]
        total_fn  = sum(len(fn_levels.get(lv,[])) for lv in level_order)

        # get category label
        cat_label = ""
        try:
            for jid, job in catalog.repository.jobs.items():
                if job.function == fn:
                    for sheet_row in []:  # placeholder
                        pass
            # look up from categories
            for cat_name, cat_fn, _ in []:
                if cat_fn == fn:
                    cat_label = cat_name
        except Exception:
            pass

        # function header
        fn_html = (
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-radius:16px;margin-bottom:16px;overflow:hidden;'
            f'box-shadow:0 1px 3px rgba(23,33,46,.05),0 12px 28px -20px rgba(23,33,46,.35)">'
            f'<div style="background:linear-gradient(135deg,{C["teal"]},{C["teal"]}CC);'
            f'padding:14px 18px;display:flex;justify-content:space-between;align-items:center">'
            f'<div>'
            f'<div style="font-family:{FONT_SERIF};font-size:19px;font-weight:600;color:#fff;'
            f'letter-spacing:-0.01em">{fn}</div></div>'
            f'<span style="font-family:{FONT_MONO};font-size:12px;font-weight:600;'
            f'background:#ffffff33;color:#fff;border-radius:999px;padding:3px 11px">'
            f'{total_fn} people</span></div>'
        )

        # level sections
        for lv in level_order:
            people = fn_levels.get(lv, [])
            if not people:
                continue
            fg, bg = LEVEL_BADGE_COL.get(lv, (C["muted"],"#F4F6F8"))
            fn_html += (
                f'<div style="padding:12px 18px;border-bottom:1px solid {C["line-2"] if hasattr(C,"line-2") else "#EEF1F4"}">'
                f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.14em;'
                f'text-transform:uppercase;color:{fg};margin-bottom:8px;'
                f'display:flex;align-items:center;gap:8px">'
                f'<span style="width:8px;height:8px;border-radius:50%;background:{fg};display:inline-block"></span>'
                f'{lv}</div>'
                f'<div style="display:flex;flex-direction:column;gap:6px">'
            )
            for p in people:
                name_part = (
                    f'<span style="font-family:{FONT_SANS};font-size:13px;font-weight:600;'
                    f'color:{C["ink"]}">{p["name"]}</span> '
                    f'<span style="font-family:{FONT_MONO};font-size:11px;color:{C["muted"]}">·</span> '
                ) if p["name"] else ""
                next_part = (
                    f' <span style="font-family:{FONT_MONO};font-size:10px;color:{C["teal"]};'
                    f'margin-left:6px">→ {p["next_role"]}</span>'
                ) if p["next_role"] else ""
                conf_col = C["teal"] if p["confidence"]>=96 else (C["amber"] if p["confidence"]>=80 else C["clay"])
                fn_html += (
                    f'<div style="display:flex;align-items:center;justify-content:space-between;'
                    f'padding:7px 10px;background:{bg};border-radius:8px;flex-wrap:wrap;gap:4px">'
                    f'<div style="flex:1">'
                    f'{name_part}'
                    f'<span style="font-family:{FONT_SANS};font-size:13px;color:{C["ink"]}">{p["std_title"]}</span>'
                    f'{next_part}</div>'
                    f'<div style="display:flex;align-items:center;gap:6px;flex-shrink:0">'
                    f'<span style="font-family:{FONT_MONO};font-size:10px;font-weight:600;color:{conf_col}">'
                    f'{p["confidence"]}%</span>'
                    f'<span style="font-family:{FONT_MONO};font-size:9px;color:{C["muted"]}">{p["match_type"]}</span>'
                    f'</div></div>'
                )
            fn_html += '</div></div>'

        fn_html += '</div>'
        st.markdown(fn_html, unsafe_allow_html=True)

    # ── export ────────────────────────────────────────────────────────────
    import io, pandas as pd_exp
    rows = []
    for fn in fn_order:
        for lv in level_order:
            for p in tree[fn].get(lv,[]):
                rows.append({
                    "Function":    fn,
                    "Level":       lv,
                    "Name":        p["name"] or "",
                    "Input Title": p["title"],
                    "Matched Role":p["std_title"],
                    "Confidence":  p["confidence"],
                    "Match Type":  p["match_type"],
                    "Next Role":   p["next_role"],
                })
    if rows:
        exp_df = pd_exp.DataFrame(rows)
        buf = io.BytesIO()
        exp_df.to_excel(buf, index=False)
        st.download_button(
            "⬇  Download org structure (.xlsx)",
            data=buf.getvalue(),
            file_name="jobsy_org_hierarchy.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

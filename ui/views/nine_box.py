"""ui/views/nine_box.py — moved verbatim out of ui/app.py on 2026-09-03."""

from __future__ import annotations

from ui.shared import *  # noqa: F401,F403


def nine_box_page(catalog):
    """9-box grid: Performance × Potential for succession weighting."""
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">9-Box Grid</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Plot employees on the performance × potential matrix. '
        f'Scores feed succession weighting.</p>',
        unsafe_allow_html=True,
    )

    results   = st.session_state.get("last_results",[])
    df_input  = st.session_state.get("upload_df")
    title_col = st.session_state.get("upload_title_col","JobTitle")

    import pandas as _pd9, io as _io9

    fn_col = next((c for c in (df_input.columns if df_input is not None else [])
                   if c.lower() in ["firstname","first_name"]), None)
    ln_col = next((c for c in (df_input.columns if df_input is not None else [])
                   if c.lower() in ["lastname","last_name"]), None)
    id_col = next((c for c in (df_input.columns if df_input is not None else [])
                   if c.lower() in ["employeeid","employee_id","id"]), None)

    def get_name(idx):
        if df_input is None or idx >= len(df_input): return f"Employee {idx+1}"
        row = df_input.iloc[idx]
        if fn_col and ln_col: return (str(row.get(fn_col,""))+" "+str(row.get(ln_col,""))).strip()
        return str(row.get(id_col,f"Employee {idx+1}"))

    # ── Load or initialise ratings ───────────────────────────────────────
    if "ninebox_ratings" not in st.session_state:
        st.session_state["ninebox_ratings"] = {}
    ratings = st.session_state["ninebox_ratings"]

    tab_input, tab_grid, tab_export = st.tabs(["Rate Employees","View Grid","Export"])

    PERF_LABELS = {1:"Low performer",2:"Effective performer",3:"Top performer"}
    POT_LABELS  = {1:"Limited potential",2:"Growth potential",3:"High potential"}
    BOX_LABELS  = {
        (3,3):"Star","(3,2)":"High performer","(3,1)":"Solid professional",
        (2,3):"Future star","(2,2)":"Core contributor","(2,1)":"Effective specialist",
        (1,3):"Rough diamond","(1,2)":"Inconsistent player","(1,1)":"Underperformer",
    }
    BOX_COLORS = {
        (3,3):"#0E7C66",(3,2):"#2B9E7E",(3,1):"#4DB89A",
        (2,3):"#2B5FA6",(2,2):"#5A7FC5",(2,1):"#8EA8DC",
        (1,3):"#B9791A",(1,2):"#D4955E",(1,1):"#E8B894",
    }

    def box_label(perf, pot):
        return BOX_LABELS.get((perf,pot), BOX_LABELS.get(f"({perf},{pot})", ""))

    # ── Tab 1: Rate ──────────────────────────────────────────────────────
    with tab_input:
        if not results:
            st.info("Run a match on the Matching page first.")
        else:
            matched_all = [(i,r) for i,r in enumerate(results) if r.matched]

            # Auto-seed ratings from the workforce file if it carries Performance/Potential
            # columns (keyed by row index so it always aligns with get_name).
            if df_input is not None and not ratings:
                _pc = next((c for c in df_input.columns if "perf" in c.lower()), None)
                _ptc = next((c for c in df_input.columns if "pot" in c.lower()), None)
                if _pc and _ptc:
                    _seeded = 0
                    for _i, _r in matched_all:
                        if _i < len(df_input):
                            try:
                                _p = max(1, min(3, int(float(df_input.iloc[_i][_pc]))))
                                _pt = max(1, min(3, int(float(df_input.iloc[_i][_ptc]))))
                                ratings[get_name(_i)] = (_p, _pt)
                                _seeded += 1
                            except Exception:
                                pass
                    if _seeded:
                        st.session_state["ninebox_ratings"] = ratings
                        st.caption(f"↩ Seeded **{_seeded}** ratings from Performance/Potential columns "
                                   "in your uploaded workforce file — edit below if needed.")

            col_a, col_b = st.columns([1,1])
            with col_a:
                # Download template pre-filled with all employees
                tmpl_rows = [{"Employee": get_name(i), "Role": r.standard_title,
                              "Performance (1-3)": "", "Potential (1-3)": ""}
                             for i,r in matched_all]
                tmpl_r = _pd9.DataFrame(tmpl_rows)
                tbuf = _io9.BytesIO(); tmpl_r.to_excel(tbuf, index=False)
                st.download_button("⬇ Download template", tbuf.getvalue(),
                    file_name="jobsy_9box_template.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            with col_b:
                upload_r = st.file_uploader("Upload completed ratings",
                                             type=["csv","xlsx"], key="nb_upload",
                                             label_visibility="collapsed")

            if upload_r:
                df_r = _pd9.read_csv(upload_r) if upload_r.name.endswith(".csv") else _pd9.read_excel(upload_r)
                ic  = next((c for c in df_r.columns if c.lower() in ["employee","employeeid","name","id"]), df_r.columns[0])
                pc  = next((c for c in df_r.columns if "perf" in c.lower()), None)
                ptc = next((c for c in df_r.columns if "pot" in c.lower()), None)
                if pc and ptc:
                    loaded = 0
                    for _, row in df_r.iterrows():
                        key = str(row[ic]).strip()
                        try:
                            p  = max(1, min(3, int(float(row[pc]))))
                            pt = max(1, min(3, int(float(row[ptc]))))
                            ratings[key] = (p, pt)
                            loaded += 1
                        except: pass
                    st.session_state["ninebox_ratings"] = ratings
                    st.success(f"✓ Loaded ratings for **{loaded}** employees.")
                else:
                    st.error("File needs: Employee/Name column, Performance (1-3), Potential (1-3)")

            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

            # Build editable table — only pre-fill employees already in ratings
            # New employees start blank (not auto-(2,2))
            table_rows = []
            for i, r in matched_all:
                emp = get_name(i)
                if emp in ratings:
                    p, pt = ratings[emp]
                else:
                    p, pt = None, None
                table_rows.append({
                    "Employee":    emp,
                    "Role":        r.standard_title,
                    "Performance": p,
                    "Potential":   pt,
                })
            df_edit = _pd9.DataFrame(table_rows)

            st.caption(f"{len(ratings)} of {len(matched_all)} employees rated — edit the table below then tap **Save ratings**")

            edited = st.data_editor(
                df_edit,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                column_config={
                    "Employee": st.column_config.TextColumn("Employee", disabled=True, width="medium"),
                    "Role":     st.column_config.TextColumn("Role",     disabled=True, width="medium"),
                    "Performance": st.column_config.NumberColumn(
                        "Performance (1–3)",
                        help="1 = Low, 2 = Effective, 3 = Top performer",
                        min_value=1, max_value=3, step=1, width="small"),
                    "Potential": st.column_config.NumberColumn(
                        "Potential (1–3)",
                        help="1 = Limited, 2 = Growth, 3 = High potential",
                        min_value=1, max_value=3, step=1, width="small"),
                },
                key="nb_editor",
            )

            if st.button("Save ratings", type="primary"):
                saved = 0
                for _, row in edited.iterrows():
                    emp = str(row["Employee"]).strip()
                    p_v = row["Performance"]
                    pt_v= row["Potential"]
                    if p_v is not None and pt_v is not None:
                        try:
                            ratings[emp] = (max(1,min(3,int(p_v))), max(1,min(3,int(pt_v))))
                            saved += 1
                        except: pass
                st.session_state["ninebox_ratings"] = ratings
                st.success(f"✓ Saved ratings for **{saved}** employees. Switch to View Grid.")
                st.rerun()

    # ── Tab 2: Grid ──────────────────────────────────────────────────────
    with tab_grid:
        if not ratings:
            st.info("Rate some employees in the Rate tab first.")
        else:
            # Build grid HTML
            grid_w, grid_h = 3, 3
            cells = {(p,pt):[] for p in range(1,4) for pt in range(1,4)}
            for emp, (p,pt) in ratings.items():
                cells[(p,pt)].append(emp)

            total_rated = len(ratings)
            stars = len(cells.get((3,3),[]))
            rough = len(cells.get((1,3),[]))
            under = len(cells.get((1,1),[]))
            st.markdown(
                f'<div style="display:flex;gap:10px;margin-bottom:16px">'
                f'{_stat_card(total_rated,"Rated")}'
                f'{_stat_card(stars,"Stars",C["teal"])}'
                f'{_stat_card(rough,"Rough diamonds",C["amber"])}'
                f'{_stat_card(under,"Underperformers",C["clay"])}'
                f'</div>', unsafe_allow_html=True)

            # Render 3x3 grid
            html = (
                f'<div style="overflow-x:auto">'
                f'<div style="display:grid;grid-template-columns:28px repeat(3,1fr);'
                f'grid-template-rows:repeat(3,1fr) 28px;gap:4px;min-width:300px">'
            )
            # Y-axis labels (potential, top to bottom: 3→1)
            pot_labels_ord = [3,2,1]
            for pt in pot_labels_ord:
                html += (f'<div style="display:flex;align-items:center;justify-content:center;'
                    f'font-family:{FONT_MONO};font-size:9px;color:{C["muted"]};'
                    f'writing-mode:vertical-lr;transform:rotate(180deg)">'
                    f'{POT_LABELS[pt][:8]}</div>')
                for p in [1,2,3]:
                    emps = cells.get((p,pt),[])
                    bc   = BOX_COLORS.get((p,pt),"#EDF0F3")
                    bl   = box_label(p,pt)
                    emp_chips = "".join(
                        f'<div style="font-family:{FONT_SANS};font-size:10px;color:#fff;'
                        f'background:rgba(0,0,0,0.2);border-radius:4px;padding:2px 5px;'
                        f'margin:1px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
                        f'max-width:100%">{e}</div>'
                        for e in emps[:6]
                    )
                    more = f'<div style="font-family:{FONT_MONO};font-size:9px;color:rgba(255,255,255,0.7)">+{len(emps)-6} more</div>' if len(emps)>6 else ""
                    html += (
                        f'<div style="background:{bc};border-radius:8px;padding:8px 10px;min-height:80px;">'
                        f'<div style="font-family:{FONT_MONO};font-size:9px;font-weight:600;'
                        f'color:rgba(255,255,255,0.8);letter-spacing:.08em;margin-bottom:4px">'
                        f'{bl}</div>'
                        f'{emp_chips}{more}'
                        f'</div>'
                    )
            # X-axis labels
            html += '<div></div>'
            for lbl in ["Low","Effective","Top"]:
                html += (f'<div style="text-align:center;font-family:{FONT_MONO};font-size:9px;'
                    f'color:{C["muted"]};padding-top:4px">{lbl} performer</div>')
            html += '</div></div>'

            # Axis titles
            st.markdown(
                f'<div style="display:flex;justify-content:center;font-family:{FONT_MONO};'
                f'font-size:10px;color:{C["muted"]};letter-spacing:.1em;margin-bottom:4px">'
                f'PERFORMANCE →</div>',
                unsafe_allow_html=True,
            )
            st.markdown(html, unsafe_allow_html=True)

    # ── Tab 3: Export ────────────────────────────────────────────────────
    with tab_export:
        if not ratings:
            st.info("Rate some employees first.")
        else:
            rows_ex = []
            for emp,(p,pt) in ratings.items():
                rows_ex.append({"Employee":emp,"Performance":p,"Potential":pt,
                    "Performance Label":PERF_LABELS[p],"Potential Label":POT_LABELS[pt],
                    "Box":box_label(p,pt)})
            df_ex = _pd9.DataFrame(rows_ex).sort_values(["Performance","Potential"],ascending=[False,False])
            st.dataframe(df_ex, use_container_width=True, hide_index=True)
            buf_ex = _io9.BytesIO(); df_ex.to_excel(buf_ex,index=False)
            st.download_button("⬇ Download 9-box report", buf_ex.getvalue(),
                file_name="jobsy_9box_grid.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

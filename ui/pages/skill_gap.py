"""ui/pages/skill_gap.py — moved verbatim out of ui/app.py on 2026-09-03."""

from __future__ import annotations

from ui.shared import *  # noqa: F401,F403


def skill_gap_page(catalog, service):
    """Skill Gap & Succession — three sub-tabs."""
    LEVEL_NAMES = {0:"None",1:"Awareness",2:"Developing",3:"Proficient",4:"Advanced",5:"Expert"}
    LEVEL_SORT  = {"Junior":1,"Medior":2,"Senior":3,"Lead":4}

    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Skill Gap & Succession</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Role gaps, batch overview, and succession readiness.</p>',
        unsafe_allow_html=True,
    )

    if not getattr(catalog.repository, "skills", None):
        st.warning("Skills data requires the **Reference workbook**. Switch data source in the sidebar.")
        return

    tab_role, tab_batch, tab_succ, tab_risk = st.tabs(["Role Gap", "Batch Overview", "Succession Planning", "Succession Risk"])

    def readiness_score(gaps):
        if not gaps: return 0
        return round(sum(1 for g in gaps if g["gap"]<=0) / len(gaps) * 100)

    def readiness_label(score):
        if score >= 80: return "Ready now",   C["teal"]
        if score >= 55: return "6-12 months", C["amber"]
        return               "Developing",    C["clay"]

    def gap_bar(current, required, color):
        cp = (current/5)*100; rp = (required/5)*100; gw = max(0, rp-cp)
        return (f'<div style="display:flex;align-items:center;gap:8px">'
                f'<div style="flex:1;position:relative;height:6px;background:#EDF0F3;border-radius:3px">'
                f'<div style="position:absolute;top:0;bottom:0;left:0;width:{cp:.0f}%;background:#C7D1D8;border-radius:3px"></div>'
                f'<div style="position:absolute;top:-1px;bottom:-1px;left:{cp:.0f}%;width:{gw:.0f}%;'
                f'background:{color}44;border:1.5px dashed {color};border-radius:3px"></div>'
                f'</div><span style="font-family:{FONT_MONO};font-size:10px;color:{color};min-width:64px;text-align:right">'
                f'{LEVEL_NAMES.get(required,"")}</span></div>')

    def gap_card(g, show_pathway=True):
        color = C["amber"] if g["gap"]>0 else (C["teal"] if g["gap"]==0 else C["violet"])
        badge = (f'+{g["gap"]} level{"s" if g["gap"]!=1 else ""}' if g["gap"]>0 else
                 ("Ready" if g["gap"]==0 else f'Exceeds +{abs(g["gap"])}'))
        pathway = _pathway_html(g) if show_pathway and g["gap"]>0 else ""
        return (f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                f'border-left:4px solid {color};border-radius:12px;padding:12px 14px;margin-bottom:8px">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px">'
                f'<div><div style="font-family:{FONT_SANS};font-size:13px;font-weight:600;color:{C["ink"]}">{g["skill_name"]}</div>'
                f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};margin-top:2px">'
                f'{g["category"]} · {g["skill_type"]}</div></div>'
                f'<span style="font-family:{FONT_MONO};font-size:11px;font-weight:600;'
                f'background:{color}1A;color:{color};border-radius:999px;padding:3px 10px">{badge}</span></div>'
                f'{gap_bar(g["current_level"],g["required_level"],color)}'
                f'{pathway}</div>')

    # ── Tab 1: Role Gap ───────────────────────────────────────────────────
    with tab_role:
        all_jobs = sorted(catalog.repository.jobs.values(), key=lambda j:(j.function,j.standard_title))
        job_opts = {f"{j.standard_title} ({j.function} · {j.level})": j.job_id for j in all_jobs}
        col1,col2 = st.columns(2)
        with col1: from_lbl = st.selectbox("Current role",list(job_opts.keys()),key="gap_from")
        with col2: to_lbl   = st.selectbox("Target role", list(job_opts.keys()),key="gap_to",index=min(1,len(job_opts)-1))
        from_id,to_id = job_opts[from_lbl],job_opts[to_lbl]
        if from_id == to_id:
            st.info("Select a different target role.")
        else:
            cur = {req.skill_id:req.required_level for req,_ in catalog.get_role_skills(from_id)}
            try: gaps = catalog.skill_gap(cur, to_id)
            except Exception as e: st.error(str(e)); gaps=[]
            develop=[g for g in gaps if g["gap"]>0]; matches=[g for g in gaps if g["gap"]==0]; exceeds=[g for g in gaps if g["gap"]<0]
            score=readiness_score(gaps); lbl,lc=readiness_label(score)
            st.markdown(f'<div style="display:flex;gap:10px;margin:12px 0">'
                f'{_stat_card(len(develop),"Develop",C["amber"])}{_stat_card(len(matches),"Ready",C["teal"])}'
                f'{_stat_card(len(exceeds),"Exceeds",C["violet"])}{_stat_card(f"{score}%","Readiness",lc)}'
                f'</div>',unsafe_allow_html=True)
            if develop:
                st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;color:{C["amber"]};margin:14px 0 8px">Skills to develop ({len(develop)})</div>',unsafe_allow_html=True)
                st.markdown("".join(gap_card(g) for g in develop),unsafe_allow_html=True)
            if matches:
                with st.expander(f"Already proficient ({len(matches)})"): st.markdown("".join(gap_card(g) for g in matches),unsafe_allow_html=True)
            if exceeds:
                with st.expander(f"Exceeds requirement ({len(exceeds)})"): st.markdown("".join(gap_card(g) for g in exceeds),unsafe_allow_html=True)
            import io as _io, pandas as _pd
            buf=_io.BytesIO(); _pd.DataFrame(gaps).to_excel(buf,index=False)
            st.download_button("⬇ Download gap report",buf.getvalue(),file_name=f"gap_{from_id}_to_{to_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ── Tab 2: Batch Overview ─────────────────────────────────────────────
    with tab_batch:
        st.markdown(f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:14px">'
            f'Gap to next career step for every matched employee.</p>',unsafe_allow_html=True)
        results_b=st.session_state.get("last_results",[]); df_b=st.session_state.get("upload_df"); nc=st.session_state.get("upload_name_col")
        if not results_b:
            st.info("Upload a file and run a match on the Matching page first.")
        else:
            import pandas as _pd2, io as _io2
            def get_nm(idx):
                if df_b is None: return ""
                row=df_b.iloc[idx] if idx<len(df_b) else None
                if row is None: return ""
                fn=next((str(row[c]) for c in ["FirstName","first_name"] if c in df_b.columns),"")
                ln=next((str(row[c]) for c in ["LastName","last_name"] if c in df_b.columns),"")
                if fn or ln: return (fn+" "+ln).strip()
                return str(row[nc]).strip() if nc and nc in df_b.columns else ""
            rows=[]
            for idx,r in enumerate(results_b):
                if not r.matched: continue
                cp=catalog.repository.career_paths.get(r.job_id)
                nr=""; nd=nr2=ne2=sv=0; tg=""
                if cp and cp.next_job_id:
                    nj=catalog.repository.jobs.get(cp.next_job_id)
                    if nj:
                        nr=nj.standard_title
                        csk={rq.skill_id:rq.required_level for rq,_ in catalog.get_role_skills(r.job_id)}
                        try:
                            gb=catalog.skill_gap(csk,cp.next_job_id)
                            nd=sum(1 for g in gb if g["gap"]>0); nr2=sum(1 for g in gb if g["gap"]==0)
                            ne2=sum(1 for g in gb if g["gap"]<0); sv=readiness_score(gb)
                            tp=[g for g in gb if g["gap"]>0]; tg=tp[0]["skill_name"] if tp else ""
                        except: pass
                rows.append({"Name":get_nm(idx) or "—","Current Role":r.standard_title,"Function":r.function,
                    "Level":r.level,"Next Role":nr or "Top of path","Readiness %":sv,
                    "Skills to Dev":nd,"Skills Ready":nr2,"Exceeds":ne2,"Top Gap":tg,"Confidence":r.confidence})
            if rows:
                df_out=_pd2.DataFrame(rows).sort_values("Readiness %",ascending=False)
                n_ready=(df_out["Readiness %"]>=80).sum()
                st.markdown(f'<div style="display:flex;gap:10px;margin-bottom:14px">'
                    f'{_stat_card(len(df_out),"Employees")}{_stat_card(n_ready,"Ready now",C["teal"])}'
                    f'{_stat_card(f"{round(df_out[chr(82)+chr(101)+chr(97)+chr(100)+chr(105)+chr(110)+chr(101)+chr(115)+chr(115)+chr(32)+chr(37)].mean())!s}%","Avg readiness",C["blue"])}'
                    f'</div>',unsafe_allow_html=True)
                st.dataframe(df_out,use_container_width=True,hide_index=True,
                    column_config={"Readiness %":st.column_config.ProgressColumn("Readiness %",min_value=0,max_value=100,format="%d%%"),
                        "Skills to Dev":st.column_config.NumberColumn("To Develop",format="%d"),
                        "Skills Ready":st.column_config.NumberColumn("Ready",format="%d")})
                buf2=_io2.BytesIO(); df_out.to_excel(buf2,index=False)
                st.download_button("⬇ Download batch overview",buf2.getvalue(),file_name="jobsy_batch_overview.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ── Tab 3: Succession Planning ────────────────────────────────────────
    with tab_succ:
        st.markdown(f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:14px">'
            f'Find the most ready candidates for any role from your employee pool.</p>',unsafe_allow_html=True)
        results_s=st.session_state.get("last_results",[])
        if not results_s:
            st.info("Upload a file and run a match on the Matching page first.")
        else:
            all_jobs_s=sorted(catalog.repository.jobs.values(),key=lambda j:(LEVEL_SORT.get(j.level,9),j.function,j.standard_title))
            job_opts_s={f"{j.standard_title} ({j.function} · {j.level})":j.job_id for j in all_jobs_s}
            target_lbl=st.selectbox("Target role to fill",list(job_opts_s.keys()),key="succ_target")
            target_id=job_opts_s[target_lbl]
            role_pool={}
            for idx,r in enumerate(results_s):
                if r.matched: role_pool.setdefault(r.job_id,[]).append(idx)
            if not role_pool:
                st.warning("No matched employees.")
            else:
                RELATED = {"HR":{"HR","Operations","Legal"},"Finance":{"Finance","Operations","Legal"},
                    "Engineering":{"Engineering","Data","Product"},"Data":{"Data","Engineering","Product"},
                    "Product":{"Product","Engineering","Data"},"Operations":{"Operations","HR","Finance"},
                    "Sales":{"Sales","Marketing","Customer"},"Marketing":{"Marketing","Sales","Customer"},
                    "Customer":{"Customer","Sales","Operations"},"Legal":{"Legal","Finance","HR"}}
                tj=catalog.repository.jobs.get(target_id)
                t_lvl=LEVEL_SORT.get(tj.level if tj else "Lead",4)
                t_fn=tj.function if tj else ""
                rel_fns=RELATED.get(t_fn,{t_fn})
                candidates=[]
                for job_id,indices in role_pool.items():
                    if job_id==target_id: continue
                    fj=catalog.repository.jobs.get(job_id)
                    if not fj: continue
                    f_lvl=LEVEL_SORT.get(fj.level,1); delta=t_lvl-f_lvl
                    same=fj.function==t_fn; rel=fj.function in rel_fns
                    if delta<=0 and not same: continue
                    if delta>2: continue
                    if not rel: continue
                    csk={rq.skill_id:rq.required_level for rq,_ in catalog.get_role_skills(job_id)}
                    try: gs=catalog.skill_gap(csk,target_id)
                    except: gs=[]
                    raw=readiness_score(gs); nd=sum(1 for g in gs if g["gap"]>0)
                    if same and delta==1: sc=min(100,int(raw*1.15)); pipe="Primary pipeline"
                    elif same and delta==0: sc=min(100,int(raw*1.05)); pipe="Lateral"
                    else: sc=max(0,int(raw*0.90)); pipe="Cross-functional"
                    lb,lc=readiness_label(sc); tg=[g["skill_name"] for g in gs if g["gap"]>0][:2]
                    candidates.append({"current_role":fj.standard_title,"function":fj.function,"level":fj.level,
                        "headcount":len(indices),"score":sc,"n_develop":nd,"label":lb,"label_col":lc,
                        "top_gaps":tg,"pipeline":pipe,"same_fn":same})
                PO={"Primary pipeline":0,"Lateral":1,"Cross-functional":2}
                candidates.sort(key=lambda c:(PO.get(c["pipeline"],9),-c["score"],c["n_develop"]))
                if not candidates:
                    st.info("No eligible candidates found for this role.")
                else:
                    cards=""
                    LVC={"Lead":("#ECE7F7","#A87CFF"),"Senior":("#E2F1ED","#0E7C66"),"Medior":("#E6EDF7","#2B5FA6"),"Junior":("#F7EEDD","#B9791A")}
                    for i,c in enumerate(candidates[:12]):
                        lb,lf=LVC.get(c["level"],("#F4F6F8","#5A6B7A"))
                        chips="".join(f'<span style="font-family:{FONT_MONO};font-size:10px;background:#F7EEDD;color:{C["amber"]};border-radius:6px;padding:2px 8px;margin:2px 3px 0 0">{s}</span>' for s in c["top_gaps"]) or f'<span style="font-family:{FONT_MONO};font-size:10px;color:{C["teal"]}">All skills met ✓</span>'
                        cards+=(f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-left:4px solid {c["label_col"]};border-radius:12px;padding:13px 14px;margin-bottom:8px">'
                            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">'
                            f'<div style="flex:1"><div style="font-family:{FONT_SANS};font-size:13px;font-weight:600;color:{C["ink"]}">#{i+1} &nbsp;{c["current_role"]}</div>'
                            f'<div style="display:flex;align-items:center;gap:6px;margin-top:4px;flex-wrap:wrap">'
                            f'<span style="font-family:{FONT_MONO};font-size:10px;font-weight:500;background:{lb};color:{lf};border-radius:6px;padding:2px 7px">{c["level"]}</span>'
                            f'<span style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]}">{c["function"]} · {c["headcount"]} in pool · {c["pipeline"]}</span></div>'
                            f'<div style="margin-top:7px;display:flex;flex-wrap:wrap">{chips}</div></div>'
                            f'<div style="text-align:right;flex-shrink:0"><div style="font-family:{FONT_MONO};font-weight:700;font-size:22px;color:{c["label_col"]};line-height:1">{c["score"]}%</div>'
                            f'<div style="font-family:{FONT_MONO};font-size:10px;color:{c["label_col"]};margin-top:2px">{c["label"]}</div></div></div>'
                            f'<div style="margin-top:10px;height:6px;background:#EDF0F3;border-radius:3px;overflow:hidden">'
                            f'<div style="height:100%;width:{c["score"]}%;background:{c["label_col"]};border-radius:3px"></div></div></div>')
                    st.markdown(cards,unsafe_allow_html=True)
                    import io as _io3, pandas as _pd3
                    sbuf=_io3.BytesIO()
                    _pd3.DataFrame([{"Target":tj.standard_title if tj else "","Pool":c["current_role"],"Function":c["function"],
                        "Level":c["level"],"Headcount":c["headcount"],"Readiness %":c["score"],"Status":c["label"],
                        "Pipeline":c["pipeline"],"To Develop":c["n_develop"],"Top Gap 1":c["top_gaps"][0] if c["top_gaps"] else "",
                        "Top Gap 2":c["top_gaps"][1] if len(c["top_gaps"])>1 else ""} for c in candidates]).to_excel(sbuf,index=False)
                    st.download_button("⬇ Download succession report",sbuf.getvalue(),file_name=f"succession_{target_id}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


    # ══════════════════════════════════════════════════════════════════════
    # TAB 4 — SUCCESSION RISK
    # ══════════════════════════════════════════════════════════════════════
    with tab_risk:
        st.markdown(
            f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:14px">'
            f'Pipeline coverage for every Lead-level role. Flags where the organisation '
            f'has no ready successor.</p>',
            unsafe_allow_html=True,
        )
        results_r  = st.session_state.get("last_results", [])
        if not results_r:
            st.info("Upload and match a file on the Matching page first.")
        else:
            import pandas as _pdr, io as _ior

            # Build role pool from batch
            role_pool_r = {}
            for idx, r in enumerate(results_r):
                if r.matched:
                    role_pool_r.setdefault(r.job_id, []).append(idx)

            RELATED_R = {
                "HR":{"HR","Operations","Legal"},"Finance":{"Finance","Operations","Legal"},
                "Engineering":{"Engineering","Data","Product"},"Data":{"Data","Engineering","Product"},
                "Product":{"Product","Engineering","Data"},"Operations":{"Operations","HR","Finance"},
                "Sales":{"Sales","Marketing","Customer"},"Marketing":{"Marketing","Sales","Customer"},
                "Customer":{"Customer","Sales","Operations"},"Legal":{"Legal","Finance","HR"},
            }

            # Evaluate all Lead roles
            lead_roles = [j for j in catalog.repository.jobs.values() if j.level == "Lead"]
            risk_rows  = []

            for tj in sorted(lead_roles, key=lambda j: (j.function, j.standard_title)):
                ready_now = 0; near = 0; developing = 0
                for job_id, indices in role_pool_r.items():
                    if job_id == tj.job_id: continue
                    fj = catalog.repository.jobs.get(job_id)
                    if not fj: continue
                    f_lvl   = LEVEL_SORT.get(fj.level, 1)
                    t_lvl   = LEVEL_SORT.get(tj.level, 4)
                    delta   = t_lvl - f_lvl
                    same    = fj.function == tj.function
                    rel     = fj.function in RELATED_R.get(tj.function, {tj.function})
                    if delta <= 0 and not same: continue
                    if delta > 2: continue
                    if not rel: continue
                    csk = {rq.skill_id: rq.required_level for rq, _ in catalog.get_role_skills(job_id)}
                    try: gs = catalog.skill_gap(csk, tj.job_id)
                    except: gs = []
                    if same and delta == 1: sc = min(100, int(readiness_score(gs)*1.15))
                    elif same: sc = min(100, int(readiness_score(gs)*1.05))
                    else: sc = max(0, int(readiness_score(gs)*0.90))
                    n_people = len(indices)
                    if sc >= 80:   ready_now += n_people
                    elif sc >= 55: near      += n_people
                    else:          developing += n_people

                total_pipe = ready_now + near + developing
                if ready_now > 0:   risk = "Covered";  risk_col = C["teal"]
                elif total_pipe > 0: risk = "At Risk";  risk_col = C["amber"]
                else:               risk = "Critical"; risk_col = C["clay"]

                risk_rows.append({
                    "Role":         tj.standard_title,
                    "Function":     tj.function,
                    "Ready Now":    ready_now,
                    "6-12 Months":  near,
                    "Developing":   developing,
                    "Total Pipeline": total_pipe,
                    "Risk":         risk,
                    "_risk_col":    risk_col,
                })

            if not risk_rows:
                st.warning("No roles to evaluate — check data source is Reference workbook.")
            else:
                # Summary
                n_crit = sum(1 for r in risk_rows if r["Risk"]=="Critical")
                n_risk = sum(1 for r in risk_rows if r["Risk"]=="At Risk")
                n_cov  = sum(1 for r in risk_rows if r["Risk"]=="Covered")
                st.markdown(
                    f'<div style="display:flex;gap:10px;margin-bottom:16px">'
                    f'{_stat_card(n_crit,"Critical",C["clay"])}'
                    f'{_stat_card(n_risk,"At Risk",C["amber"])}'
                    f'{_stat_card(n_cov,"Covered",C["teal"])}'
                    f'</div>', unsafe_allow_html=True)

                # Risk cards
                cards_r = ""
                for row in risk_rows:
                    rc = row["_risk_col"]
                    bar_ready = (row["Ready Now"]/max(row["Total Pipeline"],1))*100 if row["Total Pipeline"] else 0
                    bar_near  = (row["6-12 Months"]/max(row["Total Pipeline"],1))*100 if row["Total Pipeline"] else 0
                    pipe_bar = (
                        f'<div style="height:8px;background:#EDF0F3;border-radius:4px;overflow:hidden;display:flex;margin-top:8px">'
                        f'<div style="height:100%;width:{bar_ready:.0f}%;background:{C["teal"]}"></div>'
                        f'<div style="height:100%;width:{bar_near:.0f}%;background:{C["amber"]}"></div>'
                        f'</div>'
                    ) if row["Total Pipeline"] > 0 else (
                        f'<div style="height:8px;background:{C["clay"]}22;border:1px dashed {C["clay"]};border-radius:4px;margin-top:8px"></div>'
                    )
                    cards_r += (
                        f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                        f'border-left:4px solid {rc};border-radius:12px;padding:12px 14px;margin-bottom:8px">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center">'
                        f'<div>'
                        f'<div style="font-family:{FONT_SANS};font-size:13px;font-weight:600;color:{C["ink"]}">{row["Role"]}</div>'
                        f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};margin-top:2px">{row["Function"]} · Lead</div>'
                        f'</div>'
                        f'<div style="text-align:right">'
                        f'<span style="font-family:{FONT_MONO};font-size:12px;font-weight:600;'
                        f'background:{rc}1A;color:{rc};border-radius:999px;padding:3px 10px">{row["Risk"]}</span>'
                        f'</div></div>'
                        f'<div style="display:flex;gap:14px;margin-top:8px">'
                        f'<span style="font-family:{FONT_MONO};font-size:11px;color:{C["teal"]}">'
                        f'✓ {row["Ready Now"]} ready now</span>'
                        f'<span style="font-family:{FONT_MONO};font-size:11px;color:{C["amber"]}">'
                        f'◑ {row["6-12 Months"]} near</span>'
                        f'<span style="font-family:{FONT_MONO};font-size:11px;color:{C["muted"]}">'
                        f'○ {row["Developing"]} developing</span>'
                        f'</div>'
                        f'{pipe_bar}</div>'
                    )
                st.markdown(cards_r, unsafe_allow_html=True)

                # Export
                export_df = _pdr.DataFrame([{k:v for k,v in r.items() if k!="_risk_col"} for r in risk_rows])
                buf_r = _ior.BytesIO(); export_df.to_excel(buf_r, index=False)
                st.download_button("⬇ Download succession risk report", buf_r.getvalue(),
                    file_name="jobsy_succession_risk.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

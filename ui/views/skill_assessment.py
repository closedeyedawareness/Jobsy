"""ui/views/skill_assessment.py — moved verbatim out of ui/app.py on 2026-09-03."""

from __future__ import annotations

from ui.shared import *  # noqa: F401,F403

# Named rather than inherited from `import *`: a dependency the import
# graph cannot see is a dependency nobody can find. The rest of what this
# module uses is chrome (theme tokens, helpers) and stays with the star.
from services.assessment_service import service_for_assessments


# ── Short skill name → reference library SkillName mapping ────────────────
# Covers abbreviated names from real HR systems and datasets
SKILL_ALIASES = {
    # Leadership & management
    "leadership":          "Team leadership and development",
    "team leadership":     "Team leadership and development",
    "people leadership":   "Team leadership and development",
    "management":          "Team leadership and development",
    "performance":         "Performance management",
    "performance management": "Performance management",
    "coaching":            "Coaching and mentoring",
    "mentoring":           "Coaching and mentoring",
    "coach":               "Coaching and mentoring",
    "change management":   "Change management",
    "change":              "Change management",
    "org design":          "Organisational design",
    "organisational design": "Organisational design",
    "strategy":            "Strategic planning",
    "strategic planning":  "Strategic planning",
    "strategic":           "Strategic planning",
    "vision":              "Strategic planning",
    "stakeholder":         "Stakeholder management",
    "stakeholder management": "Stakeholder management",
    "influence":           "Stakeholder management",
    "influencing":         "Stakeholder management",
    "board":               "Board and executive advisory",
    "governance":          "Board and executive advisory",
    "executive":           "Board and executive advisory",
    "budget":              "Budget and resource management",
    "budgeting":           "Budget and resource management",
    "resource management": "Budget and resource management",
    # Technical
    "python":              "Python programming",
    "javascript":          "JavaScript and TypeScript",
    "typescript":          "JavaScript and TypeScript",
    "js":                  "JavaScript and TypeScript",
    "sql":                 "SQL and database querying",
    "database":            "SQL and database querying",
    "querying":            "SQL and database querying",
    "git":                 "Git and version control",
    "version control":     "Git and version control",
    "tdd":                 "Test-driven development",
    "testing":             "Test-driven development",
    "api":                 "API design and integration",
    "api design":          "API design and integration",
    "architecture":        "System and solution architecture",
    "system architecture": "System and solution architecture",
    "solution architecture": "System and solution architecture",
    "cloud":               "Cloud infrastructure",
    "aws":                 "Cloud infrastructure",
    "azure":               "Cloud infrastructure",
    "gcp":                 "Cloud infrastructure",
    "infrastructure":      "Cloud infrastructure",
    "iac":                 "Infrastructure as code",
    "terraform":           "Infrastructure as code",
    "kubernetes":          "Container orchestration",
    "docker":              "Container orchestration",
    "containers":          "Container orchestration",
    "ci/cd":               "CI/CD pipeline engineering",
    "cicd":                "CI/CD pipeline engineering",
    "devops":              "CI/CD pipeline engineering",
    "frontend":            "Frontend development",
    "react":               "Frontend development",
    "vue":                 "Frontend development",
    "cybersecurity":       "Security engineering",
    "security":            "Security engineering",
    # Data & analytics
    "data analysis":       "Data analysis and visualisation",
    "analytics":           "Data analysis and visualisation",
    "analysis":            "Data analysis and visualisation",
    "visualisation":       "Data analysis and visualisation",
    "visualization":       "Data analysis and visualisation",
    "statistics":          "Statistical modelling",
    "statistical":         "Statistical modelling",
    "machine learning":    "Machine learning and AI",
    "ml":                  "Machine learning and AI",
    "ai":                  "Machine learning and AI",
    "data engineering":    "Data pipeline engineering",
    "etl":                 "Data pipeline engineering",
    "pipelines":           "Data pipeline engineering",
    "bi":                  "Business intelligence",
    "business intelligence": "Business intelligence",
    "excel":               "Excel and spreadsheet modelling",
    "spreadsheet":         "Excel and spreadsheet modelling",
    "microsoft 365":       "Excel and spreadsheet modelling",
    "power bi":            "Power BI or Tableau",
    "tableau":             "Power BI or Tableau",
    "looker":              "Power BI or Tableau",
    "dashboards":          "Power BI or Tableau",
    "ab testing":          "A/B testing and experimentation",
    "experimentation":     "A/B testing and experimentation",
    "data governance":     "Data governance and quality",
    "accuracy":            "Data governance and quality",
    "data quality":        "Data governance and quality",
    "product analytics":   "Product and user analytics",
    # Finance
    "bookkeeping":         "Bookkeeping and ledger management",
    "accounting":          "Bookkeeping and ledger management",
    "ledger":              "Bookkeeping and ledger management",
    "financial reporting": "Financial reporting",
    "ifrs":                "Financial reporting",
    "gaap":                "Financial reporting",
    "finance":             "Financial reporting",
    "reporting":           "Financial reporting",
    "financial planning":  "Budgeting and financial planning",
    "planning":            "Budgeting and financial planning",
    "financial modelling": "Financial modelling",
    "modelling":           "Financial modelling",
    "corporate finance":   "Financial modelling",
    "tax":                 "Tax compliance",
    "vat":                 "Tax compliance",
    "btw":                 "Tax compliance",
    "audit":               "Audit coordination",
    "treasury":            "Treasury and cash management",
    "cash":                "Treasury and cash management",
    "management accounts": "Management accounting",
    "management accounting": "Management accounting",
    "sap":                 "Management accounting",
    # Commercial
    "sales":               "Sales prospecting and pipeline",
    "prospecting":         "Sales prospecting and pipeline",
    "pipeline":            "Sales prospecting and pipeline",
    "account management":  "Account management",
    "accounts":            "Account management",
    "crm":                 "Account management",
    "negotiation":         "Commercial negotiation",
    "deals":               "Commercial negotiation",
    "business development": "Business development",
    "biz dev":             "Business development",
    "bd":                  "Business development",
    "go-to-market":        "Go-to-market planning",
    "gtm":                 "Go-to-market planning",
    "forecasting":         "Revenue forecasting",
    "revenue":             "Revenue forecasting",
    "customer success":    "Customer success management",
    "cs":                  "Customer success management",
    "csm":                 "Customer success management",
    "pricing":             "Pricing and monetisation",
    "monetisation":        "Pricing and monetisation",
    "tender":              "Tender and bid management",
    "bids":                "Tender and bid management",
    # Marketing
    "seo":                 "SEO and search marketing",
    "search marketing":    "SEO and search marketing",
    "paid media":          "Digital advertising",
    "google ads":          "Digital advertising",
    "digital advertising": "Digital advertising",
    "email marketing":     "Email marketing and automation",
    "email":               "Email marketing and automation",
    "content":             "Content strategy and creation",
    "copywriting":         "Content strategy and creation",
    "brand":               "Brand management",
    "branding":            "Brand management",
    "web analytics":       "Web and campaign analytics",
    "ga4":                 "Web and campaign analytics",
    "social media":        "Social media management",
    "social":              "Social media management",
    "campaigns":           "Marketing campaign management",
    "campaign management": "Marketing campaign management",
    # HR
    "labour law":          "Dutch labour law",
    "employment law":      "Dutch labour law",
    "dutch law":           "Dutch labour law",
    "hr policy":           "HR policy and compliance",
    "policy":              "HR policy and compliance",
    "compliance":          "HR policy and compliance",
    "talent management":   "Talent management and succession",
    "succession":          "Talent management and succession",
    "talent":              "Talent management and succession",
    "workforce planning":  "Workforce planning",
    "people strategy":     "Workforce planning",
    "headcount":           "Workforce planning",
    "employee relations":  "Employee relations and casework",
    "er":                  "Employee relations and casework",
    "casework":            "Employee relations and casework",
    "compensation":        "Compensation and benefits",
    "benefits":            "Compensation and benefits",
    "total rewards":       "Compensation and benefits",
    "hris":                "HRIS and HR administration",
    "hr systems":          "HRIS and HR administration",
    "recruitment":         "Recruitment and employer branding",
    "hiring":              "Recruitment and employer branding",
    "talent acquisition":  "Recruitment and employer branding",
    "employer branding":   "Recruitment and employer branding",
    # Professional
    "project management":  "Project management",
    "projects":            "Project management",
    "pm":                  "Project management",
    "process improvement": "Process improvement",
    "lean":                "Process improvement",
    "six sigma":           "Process improvement",
    "risk management":     "Risk and compliance management",
    "risk":                "Risk and compliance management",
    "communication":       "Written and verbal communication",
    "presentation":        "Written and verbal communication",
    "writing":             "Written and verbal communication",
    "teamwork":            "Written and verbal communication",
    "data driven":         "Data-driven decision making",
    "decision making":     "Data-driven decision making",
    "problem solving":     "Problem structuring and solving",
    "problem-solving":     "Problem structuring and solving",
    "innovation":          "Problem structuring and solving",
    "adaptability":        "Change management",
    "gdpr":                "GDPR and data privacy",
    "privacy":             "GDPR and data privacy",
    "avg":                 "GDPR and data privacy",
    "contracts":           "Contract and legal advisory",
    "legal":               "Contract and legal advisory",
    "requirements":        "Requirements analysis",
    "customer focus":      "Customer success management",
    "regulatory":          "Regulatory compliance",
}


def _resolve_skill_name(raw_name, skill_name_to_id):
    """Map a raw/short skill name to a reference library skill ID."""
    raw = raw_name.strip().lower()
    # 1. exact match in reference library
    if raw in skill_name_to_id:
        return skill_name_to_id[raw]
    # 2. alias lookup
    alias_target = SKILL_ALIASES.get(raw)
    if alias_target and alias_target.lower() in skill_name_to_id:
        return skill_name_to_id[alias_target.lower()]
    # 3. partial match — raw is a substring of a skill name
    for sk_name, sk_id in skill_name_to_id.items():
        if raw in sk_name or sk_name in raw:
            return sk_id
    return None


LEVEL_TEXT_MAP = {
    "awareness":1,"beginner":1,"novice":1,"basic":1,
    "developing":2,"learning":2,"intermediate":2,"foundation":2,
    "proficient":3,"competent":3,"skilled":3,"practiced":3,
    "advanced":4,"experienced":4,"strong":4,"senior":4,
    "expert":5,"master":5,"authority":5,"distinguished":5,
    "1":1,"2":2,"3":3,"4":4,"5":5,
}


def skill_assessment_page(catalog):
    """Upload individual skill assessments — actual levels per person per skill."""
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Skills Assessment</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Upload actual assessed skill levels per person. These replace role-assumed '
        f'levels in gap analysis for a true individual view.</p>',
        unsafe_allow_html=True,
    )

    import pandas as _pdsa, io as _iosa

    if not getattr(catalog.repository, "skills", None):
        st.warning("Skills data requires the **Reference workbook**.")
        return

    # ── Template download ────────────────────────────────────────────────
    skills_list = sorted(catalog.repository.skills.values(), key=lambda s: (s.category, s.skill_name))
    tmpl_cols   = ["EmployeeID","Name","CurrentRole"] + [s.skill_name for s in skills_list]
    tmpl_df     = _pdsa.DataFrame(columns=tmpl_cols)
    # Add two sample rows
    sample_skills = {s.skill_name: "" for s in skills_list}
    tmpl_df = _pdsa.concat([tmpl_df, _pdsa.DataFrame([
        {"EmployeeID":"E1001","Name":"Eva de Vries","CurrentRole":"Chief Executive Officer", **sample_skills},
        {"EmployeeID":"E1002","Name":"Sem Meijer",  "CurrentRole":"Chief Financial Officer", **sample_skills},
    ])], ignore_index=True)
    # Behavioural rubric (1-5 anchors per skill category) — for the template + UI
    _rubric = catalog.proficiency_rubric() if hasattr(catalog, "proficiency_rubric") else {}
    _rubric_rows = [
        {"Skill Category": cat, "Level": lvl,
         "Level Name": _rubric[cat].get(lvl, {}).get("name", ""),
         "What it looks like": _rubric[cat].get(lvl, {}).get("anchor", "")}
        for cat in sorted(_rubric) for lvl in range(1, 6) if _rubric[cat].get(lvl)
    ]
    tmpl_buf = _iosa.BytesIO()
    with _pdsa.ExcelWriter(tmpl_buf, engine="openpyxl") as _xl:
        tmpl_df.to_excel(_xl, index=False, sheet_name="Assessment")
        if _rubric_rows:
            _pdsa.DataFrame(_rubric_rows).to_excel(_xl, index=False, sheet_name="Proficiency Rubric")
    _template_download("⬇ Download assessment template (.xlsx)", tmpl_buf.getvalue(),
        file_name="jobsy_skills_assessment_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ── Proficiency rubric reference ─────────────────────────────────────
    if _rubric:
        with st.expander("📊 Proficiency rubric — what levels 1–5 mean for each skill category"):
            st.caption("Score people against these behavioural anchors so ratings stay consistent "
                       "across assessors. Included as a sheet in the template above.")
            for cat in sorted(_rubric):
                rows = "".join(
                    f'<div style="display:flex;gap:10px;margin:3px 0">'
                    f'<span style="flex:0 0 24px;font-family:{FONT_MONO};font-weight:700;color:{C["teal"]}">{lvl}</span>'
                    f'<span style="flex:0 0 92px;font-family:{FONT_MONO};font-size:11px;color:{C["muted"]}">'
                    f'{_rubric[cat].get(lvl, {}).get("name", "")}</span>'
                    f'<span style="font-size:13px;color:{C["ink"]}">'
                    f'{_rubric[cat].get(lvl, {}).get("anchor", "")}</span></div>'
                    for lvl in range(1, 6) if _rubric[cat].get(lvl)
                )
                st.markdown(
                    f'<div style="margin:10px 0 6px;font-family:{FONT_SANS};font-weight:600;'
                    f'font-size:14px;color:{C["ink"]}">{cat}</div>{rows}',
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── Upload ───────────────────────────────────────────────────────────
    upload_sa = st.file_uploader("Upload completed assessment (.csv or .xlsx)",
                                  type=["csv","xlsx"], key="sa_upload")
    df_sa = None
    if upload_sa:
        df_sa = (_pdsa.read_csv(upload_sa) if upload_sa.name.endswith(".csv")
                 else _pdsa.read_excel(upload_sa))
    else:
        # Reuse the workforce file from Matching if it carries skill proficiencies.
        _wf = st.session_state.get("upload_df")
        if _wf is not None and _smart_detect(list(_wf.columns),
                {"skillproficiency", "skill proficiency", "skills", "coreskillproficiency"},
                ["proficiency", "skill"]):
            if st.checkbox(f"Use the workforce data uploaded on Matching "
                           f"({len(_wf)} rows, has skill proficiencies)", value=True, key="sa_reuse"):
                df_sa = _wf.copy()
    if df_sa is None:
        existing = st.session_state.get("skill_assessments")
        if existing:
            n_people = len(existing)
            n_skills = max((len(v) for v in existing.values()), default=0)
            st.info(
                f"✓ **{n_people} people** with up to **{n_skills} skills** loaded from your previous upload.  \n"
                f"Upload a new file to replace, or use the selector below to analyse."
            )
            _show_assessment_preview(catalog, existing)
        else:
            st.markdown(
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                f'border-radius:12px;padding:16px;color:{C["muted"]};font-size:14px;margin-top:4px">'
                f'Download the template above, fill in skill levels (1–5 or text), '
                f'then upload it here.</div>',
                unsafe_allow_html=True,
            )
        return

    skill_name_to_id = {s.skill_name.lower(): s.skill_id
                        for s in catalog.repository.skills.values()}
    assessments = {}  # {employee_key: {skill_id: level}}

    # ── Detect format ────────────────────────────────────────────────────
    lower_cols = [c.lower() for c in df_sa.columns]

    # Tagged format: columns like CoreSkillProficiency containing "SkillName:Level;..."
    proficiency_cols = [c for c in df_sa.columns
                        if any(k in c.lower() for k in ["proficiency","assessment","skills_level"])]
    plain_skill_cols = [c for c in df_sa.columns
                        if any(k in c.lower() for k in ["softskill","soft_skill"]) and "proficiency" not in c.lower()]

    is_tagged  = any(
        ":" in str(v)
        for col in proficiency_cols
        for v in df_sa[col].dropna().head(5)
    )
    is_long = ("skillname" in lower_cols or "skill_name" in lower_cols
               or "skill name" in lower_cols)

    id_col   = next((c for c in df_sa.columns if c.lower() in ["employeeid","employee_id","id"]), df_sa.columns[0])
    fn_col   = next((c for c in df_sa.columns if c.lower() in ["firstname","first_name"]), None)
    ln_col   = next((c for c in df_sa.columns if c.lower() in ["lastname","last_name"]),  None)

    def emp_key(row):
        eid = str(row[id_col]).strip()
        if fn_col and ln_col:
            name = (str(row.get(fn_col,""))+" "+str(row.get(ln_col,""))).strip()
            return f"{name} ({eid})" if name else eid
        return eid

    if is_tagged:
        # Format: CoreSkillProficiency = "Leadership:Expert;Strategy:Advanced"
        # Also SoftSkills = "Communication;Teamwork" (no levels — default to Proficient=3)
        for _, row in df_sa.iterrows():
            emp = emp_key(row)
            emp_skills = {}
            for col in proficiency_cols:
                val = str(row.get(col,"")).strip()
                if not val or val.lower() == "nan": continue
                for pair in val.split(";"):
                    pair = pair.strip()
                    if ":" in pair:
                        raw_name, raw_level = pair.rsplit(":",1)
                    else:
                        raw_name, raw_level = pair, "Proficient"
                    sid = _resolve_skill_name(raw_name.strip(), skill_name_to_id)
                    if not sid: continue
                    lv = LEVEL_TEXT_MAP.get(raw_level.strip().lower(), 3)
                    emp_skills[sid] = lv
            for col in plain_skill_cols:
                val = str(row.get(col,"")).strip()
                if not val or val.lower() == "nan": continue
                for sk in val.split(";"):
                    sid = _resolve_skill_name(sk.strip(), skill_name_to_id)
                    if sid and sid not in emp_skills:
                        emp_skills[sid] = 3  # default Proficient for unlevelled skills
            if emp_skills:
                assessments[emp] = emp_skills

    elif is_long:
        sk_col = next((c for c in df_sa.columns if "skill" in c.lower() and "name" in c.lower()), None)
        lv_col = next((c for c in df_sa.columns if "level" in c.lower() or "score" in c.lower()), None)
        if not sk_col or not lv_col:
            st.error("Long format needs columns: [EmployeeID/Name], [SkillName], [Level]"); return
        for _, row in df_sa.iterrows():
            emp = emp_key(row)
            sid = _resolve_skill_name(str(row[sk_col]).strip(), skill_name_to_id)
            if not sid: continue
            raw_lv = str(row[lv_col]).strip().lower()
            lv = LEVEL_TEXT_MAP.get(raw_lv) or (int(float(raw_lv)) if raw_lv.replace(".","").isdigit() else 3)
            assessments.setdefault(emp, {})[sid] = max(0, min(5, lv))

    else:
        # Wide format: skill names as column headers (match via alias table)
        skill_cols = [c for c in df_sa.columns
                      if _resolve_skill_name(c, skill_name_to_id) is not None]
        if not skill_cols:
            st.warning(
                "No skill columns recognised. Either:\n"
                "- Use the **Download template** above (exact skill names pre-filled), or\n"
                "- Name columns to match the reference library (e.g. *Team leadership and development*, "
                "*SQL and database querying*, *Financial modelling*), or\n"
                "- Use the tagged format in a *Proficiency* column: `Leadership:Advanced;Finance:Expert`"
            ); return
        for _, row in df_sa.iterrows():
            emp = emp_key(row)
            emp_skills = {}
            for col in skill_cols:
                val = row[col]
                if _pdsa.isna(val) or str(val).strip() == "": continue
                raw_lv = str(val).strip().lower()
                lv = LEVEL_TEXT_MAP.get(raw_lv) or int(float(raw_lv)) if raw_lv.replace(".","").isdigit() else None
                if lv is None: continue
                sid = _resolve_skill_name(col, skill_name_to_id)
                if sid: emp_skills[sid] = max(0, min(5, lv))
            if emp_skills:
                assessments[emp] = emp_skills

    if not assessments:
        st.error("No valid skill data found. Check the file matches the template format."); return

    st.session_state["skill_assessments"] = assessments
    # Department lives on the uploaded file itself, not on SkillAssessment --
    # captured here (same emp_key so it joins back cleanly) so the Skills
    # Dashboard's declared-skills-by-department view has somewhere to read it from.
    _dept_col = next((c for c in df_sa.columns
                      if c.lower() in ("department", "dept", "afdeling", "team", "business unit")), None)
    if _dept_col:
        st.session_state["skill_assessment_departments"] = {
            emp_key(row): str(row[_dept_col]).strip()
            for _, row in df_sa.iterrows() if str(row.get(_dept_col, "")).strip()
        }
    # The person's current job title, captured the same way. This is what lets
    # AssessmentService resolve someone to their OWN role -- without it the page
    # can only answer "ready for the role you picked", never "how are they doing
    # in the job they already have".
    _title_col = next((c for c in df_sa.columns
                       if c.lower().replace(" ", "").replace("_", "") in (
                           "currentrole", "currenttitle", "jobtitle", "title",
                           "role", "functie", "functienaam")), None)
    if _title_col:
        st.session_state["skill_assessment_titles"] = {
            emp_key(row): str(row[_title_col]).strip()
            for _, row in df_sa.iterrows() if str(row.get(_title_col, "")).strip()
        }
    st.success(f"✓ Loaded assessments for **{len(assessments)} people** covering "
               f"{max(len(v) for v in assessments.values())} skills each.")
    _show_assessment_preview(catalog, assessments)


def _render_own_role_coverage(catalog, assessments, selected):
    """Coverage against the person's OWN role, plus their next career step.

    Everything below comes from AssessmentService, which joins SkillAssessment to
    RoleSkillRequirement. Two things differ from the target-role analysis further
    down the page: coverage is weighted by required level (a Core-5 gap counts for
    more than an Adjacent-2, where a flat count treats them alike), and the next
    role comes from the CareerStep already in the library rather than from a guess.
    """
    titles = st.session_state.get("skill_assessment_titles") or {}
    try:
        svc = service_for_assessments(catalog, assessments, titles=titles, source="self")
        cov  = svc.coverage_for_employee(selected)
        opps = svc.career_opportunities(selected)
    except Exception as exc:                       # never take the page down
        import logging
        logging.getLogger("jobsy").warning(
            "Own-role coverage unavailable for %r: %s", selected, exc)
        return

    st.markdown(
        f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
        f'text-transform:uppercase;color:{C["muted"]};margin:18px 0 8px">'
        f'Against their own role</div>', unsafe_allow_html=True)

    if not cov.job_id:
        _t = titles.get(selected, "")
        st.markdown(
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-radius:12px;padding:14px 16px;color:{C["muted"]};font-size:13px">'
            + (f'No role in the library matches <b>{_t}</b>, so there is nothing to '
               f'measure them against. Use the target-role analysis below.'
               if _t else
               'This file carries no current-role column, so people can only be '
               'measured against a role you pick. Add a <b>CurrentRole</b> column '
               'to see coverage against the job they already hold.')
            + '</div>', unsafe_allow_html=True)
        return

    if not cov.gaps:
        # A role with no requirements in the library scores 1.0 by definition.
        # Showing that as "100% covered" would be the exact overclaim this page exists
        # to avoid, so say what's actually true instead.
        st.markdown(
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-radius:12px;padding:14px 16px;color:{C["muted"]};font-size:13px">'
            f'<b>{cov.job_title}</b> has no skill requirements defined in the reference '
            f'library, so there is nothing to measure coverage against. This is a gap in '
            f'the job architecture, not a finding about this person.</div>',
            unsafe_allow_html=True)
        return

    # How much of the role we actually have a reading on. Coverage without this is
    # unreadable: 11% of a role you have one data point for is not a low score, it's
    # an absent measurement, and the two must never look the same.
    n_req      = len(cov.gaps)
    n_assessed = sum(1 for g in cov.gaps if g.current_level > 0)
    measured   = n_assessed / n_req
    thin       = measured < 0.5

    pct   = round(cov.coverage * 100)
    ccol  = C["muted"] if thin else (C["teal"] if pct >= 80 else (C["amber"] if pct >= 55 else C["clay"]))
    conf  = [g.confidence for g in cov.gaps if g.current_level > 0]
    avg_c = round(sum(conf) / len(conf), 2) if conf else 0.0
    core_open = sum(1 for g in cov.open_gaps if g.skill_type == "Core")

    st.caption(f"Measured against **{cov.job_title}** — the role resolved from their own title.")
    st.markdown(
        f'<div style="display:flex;gap:10px;margin:8px 0 4px">'
        f'<div style="flex:1;background:{C["surface"]};border:1px solid {C["line"]};border-radius:14px;'
        f'padding:14px 10px;text-align:center">'
        f'<div style="font-family:{FONT_MONO};font-weight:600;font-size:26px;color:{ccol}">{pct}%</div>'
        f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};letter-spacing:.1em">'
        f'ROLE COVERAGE</div></div>'
        f'{_stat_card(f"{n_assessed}/{n_req}", "Requirements Read", C["clay"] if thin else C["teal"])}'
        f'{_stat_card(core_open, "Core Gaps", C["clay"] if core_open else C["teal"])}'
        f'{_stat_card(avg_c, "Confidence", C["muted"])}'
        f'</div>', unsafe_allow_html=True)

    if thin:
        st.warning(
            f"**Read this as an absent measurement, not a low score.** Only "
            f"{n_assessed} of {cov.job_title}'s {n_req} required skills have any "
            f"assessment behind them; the other {n_req - n_assessed} have never been "
            f"rated, and an unrated skill counts as zero. Capture assessments against "
            f"the skill catalogue — using the template above — before reading the "
            f"percentage as capability."
        )
    else:
        st.caption(
            "Coverage is weighted by required level, so a Core-5 shortfall counts for more "
            "than an Adjacent-2. Confidence is the mean across assessed skills — self-rated "
            "readings sit at 0.5 and only rise when someone validates them."
        )

    for o in opps:
        rpct  = round(o.readiness * 100)
        o_read = sum(1 for g in o.gaps if g.current_level > 0)
        o_thin = bool(o.gaps) and (o_read / len(o.gaps)) < 0.5
        rcol  = C["muted"] if o_thin else (C["teal"] if o.ready else C["amber"])
        state = ("too little assessed to say" if o_thin
                 else ("Ready now" if o.ready else f"{len(o.open_gaps)} to close"))
        st.markdown(
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-left:4px solid {rcol};border-radius:12px;padding:12px 14px;margin:10px 0 0">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<div><div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};'
            f'letter-spacing:.1em">NEXT STEP</div>'
            f'<div style="font-family:{FONT_SANS};font-size:14px;font-weight:600;color:{C["ink"]}">'
            f'{o.to_title}</div></div>'
            f'<span style="font-family:{FONT_MONO};font-size:11px;font-weight:600;'
            f'background:{rcol}1A;color:{rcol};border-radius:999px;padding:3px 10px">'
            + (state if o_thin else f'{rpct}% · {state}')
            + '</span></div></div>', unsafe_allow_html=True)
        if o.open_gaps:
            with st.expander(f"What stands between them and {o.to_title}"):
                st.markdown("".join(
                    f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
                    f'border-bottom:1px solid {C["line"]};font-size:13px;color:{C["ink"]}">'
                    f'<span>{g.skill_name} '
                    f'<span style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]}">'
                    f'{g.skill_type}</span></span>'
                    f'<span style="font-family:{FONT_MONO};font-size:11px;color:{C["amber"]}">'
                    f'{g.current_level} → {g.required_level}</span></div>'
                    for g in o.open_gaps), unsafe_allow_html=True)

    if not opps:
        st.caption("No onward career step is defined for this role in the library.")


def _show_assessment_preview(catalog, assessments):
    """Show a summary and per-person gap analysis using actual assessed levels."""
    import pandas as _pdp

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    emp_list = sorted(assessments.keys())
    selected = st.selectbox("View individual gap analysis for:", emp_list, key="sa_emp_sel")
    if not selected: return

    emp_skills = assessments[selected]
    assessed_count = len(emp_skills)
    avg_level = round(sum(emp_skills.values())/assessed_count, 1) if assessed_count else 0

    st.markdown(
        f'<div style="display:flex;gap:10px;margin:12px 0">'
        f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-radius:12px;'
        f'padding:14px 18px;flex:1;text-align:center">'
        f'<div style="font-size:24px;font-weight:700;color:{C["teal"]}">{assessed_count}</div>'
        f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};letter-spacing:.1em">SKILLS ASSESSED</div></div>'
        f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-radius:12px;'
        f'padding:14px 18px;flex:1;text-align:center">'
        f'<div style="font-size:24px;font-weight:700;color:{C["blue"]}">{avg_level}</div>'
        f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};letter-spacing:.1em">AVG LEVEL</div></div>'
        f'</div>', unsafe_allow_html=True)

    _render_own_role_coverage(catalog, assessments, selected)

    # target role selector
    all_jobs = sorted(catalog.repository.jobs.values(), key=lambda j:(j.function,j.standard_title))
    job_opts = {f"{j.standard_title} ({j.function} · {j.level})": j.job_id for j in all_jobs}
    target_lbl = st.selectbox("Assess readiness for target role:", list(job_opts.keys()), key="sa_target")
    target_id  = job_opts[target_lbl]

    try:
        gaps   = catalog.skill_gap(emp_skills, target_id)
    except Exception as e:
        st.error(str(e)); return

    develop = [g for g in gaps if g["gap"]>0]
    matches = [g for g in gaps if g["gap"]==0]
    exceeds = [g for g in gaps if g["gap"]<0]
    LEVEL_NAMES = {0:"None",1:"Awareness",2:"Developing",3:"Proficient",4:"Advanced",5:"Expert"}

    def rs(gs): return round(sum(1 for g in gs if g["gap"]<=0)/len(gs)*100) if gs else 0
    score = rs(gaps)
    lbl   = "Ready now" if score>=80 else ("6–12 months" if score>=55 else "Developing")
    lc    = C["teal"] if score>=80 else (C["amber"] if score>=55 else C["clay"])

    st.markdown(
        f'<div style="display:flex;gap:10px;margin:12px 0">'
        f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-radius:12px;'
        f'padding:14px 18px;flex:1;text-align:center">'
        f'<div style="font-size:26px;font-weight:700;color:{lc}">{score}%</div>'
        f'<div style="font-family:{FONT_MONO};font-size:10px;color:{lc};letter-spacing:.1em">{lbl.upper()}</div></div>'
        f'{_stat_card(len(develop),"To Develop",C["amber"])}'
        f'{_stat_card(len(matches),"Ready",C["teal"])}'
        f'</div>', unsafe_allow_html=True)

    if develop:
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:{C["amber"]};margin:14px 0 8px">'
            f'Skills to develop — {selected}</div>', unsafe_allow_html=True)
        cards = ""
        for g in develop:
            color = C["amber"]
            cp=(g["current_level"]/5)*100; rp=(g["required_level"]/5)*100; gw=max(0,rp-cp)
            pathway = _pathway_html(g)
            cards += (
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                f'border-left:4px solid {color};border-radius:12px;padding:12px 14px;margin-bottom:8px">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px">'
                f'<div><div style="font-family:{FONT_SANS};font-size:13px;font-weight:600;color:{C["ink"]}">{g["skill_name"]}</div>'
                f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};margin-top:2px">{g["category"]} · {g["skill_type"]}</div></div>'
                f'<span style="font-family:{FONT_MONO};font-size:11px;font-weight:600;background:{color}1A;'
                f'color:{color};border-radius:999px;padding:3px 10px">+{g["gap"]} level{"s" if g["gap"]!=1 else ""}</span></div>'
                f'<div style="display:flex;align-items:center;gap:8px">'
                f'<div style="flex:1;position:relative;height:6px;background:#EDF0F3;border-radius:3px">'
                f'<div style="position:absolute;top:0;bottom:0;left:0;width:{cp:.0f}%;background:{C["teal"]};border-radius:3px"></div>'
                f'<div style="position:absolute;top:-1px;bottom:-1px;left:{cp:.0f}%;width:{gw:.0f}%;'
                f'background:{color}44;border:1.5px dashed {color};border-radius:3px"></div></div>'
                f'<span style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};min-width:80px">'
                f'{LEVEL_NAMES.get(g["current_level"],"None")} → {LEVEL_NAMES.get(g["required_level"],"")}</span></div>'
                f'{pathway}</div>'
            )
        st.markdown(cards, unsafe_allow_html=True)
    if matches:
        with st.expander(f"Already proficient ({len(matches)})"):
            st.markdown("".join(
                f'<div style="padding:6px 0;border-bottom:1px solid {C["line"]};font-family:{FONT_SANS};font-size:13px;color:{C["ink"]}">'
                f'✓ {g["skill_name"]} <span style="font-family:{FONT_MONO};font-size:10px;color:{C["teal"]}">{LEVEL_NAMES.get(g["current_level"],"")}</span></div>'
                for g in matches), unsafe_allow_html=True)

    # Export personal development plan
    rows = [{"Skill":g["skill_name"],"Category":g["category"],"Type":g["skill_type"],
             "Current Level":LEVEL_NAMES.get(g["current_level"],"None"),
             "Required Level":LEVEL_NAMES.get(g["required_level"],""),
             "Gap":g["gap"],"Status":g["status"],
             "Development Action":_get_pathway(g["category"],g["gap"])[0] if g["gap"]>0 else "",
             "Method":_get_pathway(g["category"],g["gap"])[1] if g["gap"]>0 else "",
             "Estimated Duration":_get_pathway(g["category"],g["gap"])[2] if g["gap"]>0 else ""}
            for g in gaps]
    import io as _ioex, pandas as _pdex
    buf_ex = _ioex.BytesIO(); _pdex.DataFrame(rows).to_excel(buf_ex, index=False)
    _logged_download(f"⬇ Download development plan — {selected}", buf_ex.getvalue(),
        file_name=f"dev_plan_{selected.replace(' ','_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

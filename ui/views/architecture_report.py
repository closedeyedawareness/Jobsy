"""ui/views/architecture_report.py — moved verbatim out of ui/app.py on 2026-09-03."""

from __future__ import annotations

from ui.shared import *  # noqa: F401,F403


def architecture_report_page(catalog):
    """Generate a board-ready Job Architecture Framework report."""
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Architecture Report</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Generate a board-ready Job Architecture Framework with grading, '
        f'pay equity, succession risk, and strategic recommendations.</p>',
        unsafe_allow_html=True,
    )
    if ArchitectureReportService is None:
        st.error("architecture_report_service.py not found in services/")
        return

    results  = st.session_state.get("last_results", [])
    df_input = st.session_state.get("upload_df")

    if not results:
        st.info("Upload a file and run a match on the Matching page first.")
        return

    matched = [r for r in results if r.matched]
    lead_c  = sum(1 for r in matched if r.level=="Lead")
    fns     = len({r.function for r in matched})

    st.markdown(
        f'<div style="display:flex;gap:10px;margin-bottom:16px">'
        f'{_stat_card(len(matched),"Employees")}{_stat_card(fns,"Functions",C["blue"])}'
        f'{_stat_card(lead_c,"Lead roles",C["violet"])}</div>',
        unsafe_allow_html=True,
    )

    org_label = st.text_input("Organisation name for the report",
                               value=st.session_state.get("org_label","Organisation"),
                               key="arch_org_label")

    st.markdown(
        f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};margin:12px 0 8px">'
        f'Report includes 7 sections: Executive Summary · Job Architecture · Org Snapshot · '
        f'Grade Distribution · Career Paths · Succession Risk · Recommendations</div>',
        unsafe_allow_html=True,
    )

    if st.button("Generate Architecture Report", type="primary", use_container_width=True):
        with st.spinner("Analysing organisation and generating report…"):
            try:
                svc = ArchitectureReportService(
                    catalog=catalog,
                    results=results,
                    df_employees=df_input,
                    org_label=org_label,
                )
                report_bytes = svc.generate()
                import re
                safe_label = re.sub(r"[^a-zA-Z0-9_-]","_", org_label)[:30]
                from datetime import date
                fname = f"{_brand_name()}_Architecture_Report_{safe_label}_{date.today().strftime('%Y%m%d')}.xlsx"
                st.success("✓ Report generated. Download below.")
                st.download_button(
                    "⬇  Download Architecture Report (.xlsx)",
                    data=report_bytes,
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except Exception as exc:
                import traceback
                st.error(f"Report generation failed: {exc}")
                with st.expander("Details"):
                    st.code(traceback.format_exc())

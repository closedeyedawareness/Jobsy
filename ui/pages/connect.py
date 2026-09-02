"""ui/pages/connect.py — moved verbatim out of ui/app.py on 2026-09-03."""

from __future__ import annotations

from ui.shared import *  # noqa: F401,F403


def connect_page():
    """Live data connection — AFAS Profit or Workday."""
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Live Connection</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Pull employee data directly from AFAS Profit or Workday. '
        f'Credentials are session-only and never stored.</p>',
        unsafe_allow_html=True,
    )

    available = ([n for n, ok in (("AFAS Profit", _AFAS_AVAILABLE),
                                  ("Workday", _WORKDAY_AVAILABLE)) if ok])
    if not available:
        st.error("No connector modules found. Check `services/afas_connector.py` and "
                 "`services/workday_connector.py` are present.")
        return
    if len(available) == 1:
        st.warning(f"Only the {available[0]} connector is installed; the other module is missing.")

    system = (st.radio("System", available, horizontal=True, key="conn_system")
              if len(available) > 1 else available[0])
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── AFAS ──────────────────────────────────────────────────────────────
    if system == "AFAS Profit":
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.1em;'
            f'text-transform:uppercase;color:{C["muted"]};margin-bottom:12px">'
            f'AFAS Profit REST API</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            env_id = st.text_input("Environment ID", placeholder="12345",
                                   help="The number before .rest.afas.online", key="afas_env")
            afas_env_type = st.radio(
                "Environment", ["production", "test"], horizontal=True, key="afas_env_type",
                help="A test environment answers on .resttest.afas.online and needs its own token.")
            connector_name = st.text_input("Connector name", value="HrEmployee",
                                           help="GetConnector configured by your AFAS admin", key="afas_conn")
        with col2:
            token = st.text_input("API token", type="password",
                                  help="Generate in AFAS → App Connector → REST services", key="afas_token")
            max_rows = st.number_input("Max employees to fetch", value=500, min_value=10, max_value=5000, step=100)

        st.caption("Your token is masked and exists only in this browser session.")

        col_test, col_fetch = st.columns(2)
        with col_test:
            if st.button("Test connection", key="afas_test"):
                if not env_id or not token:
                    st.warning("Enter Environment ID and Token first.")
                else:
                    with st.spinner("Testing..."):
                        conn = AfasConnector(env_id, token, environment=afas_env_type)
                        ok, msg = conn.test_connection()
                    if ok:
                        st.success(f"✓ Connected to AFAS environment {env_id}")
                        connectors = conn.list_connectors()
                        if connectors:
                            st.caption(f"Available connectors: {', '.join(connectors[:10])}")
                    else:
                        st.error(f"Connection failed: {msg}")

        with col_fetch:
            if st.button("Fetch employees", type="primary", key="afas_fetch"):
                if not env_id or not token:
                    st.warning("Enter credentials first.")
                else:
                    with st.spinner(f"Fetching from {connector_name}…"):
                        try:
                            conn = AfasConnector(env_id, token, environment=afas_env_type)
                            df = conn.fetch_employees(connector_name=connector_name, take=min(1000, max_rows))
                            if df.empty:
                                st.warning("No data returned. Check the connector name.")
                            else:
                                st.session_state["upload_df"]       = df
                                st.session_state["upload_title_col"] = _detect_col(df, ["JobTitle","Functieomschrijving","functie"])
                                st.session_state["upload_name_col"]  = None
                                st.success(f"✓ Fetched **{len(df)} employees** from AFAS. Switch to Matching to run analysis.")
                                st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                        except Exception as exc:
                            st.error(f"Fetch failed: {exc}")

    # ── Workday ───────────────────────────────────────────────────────────
    else:
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.1em;'
            f'text-transform:uppercase;color:{C["muted"]};margin-bottom:12px">'
            f'Workday REST API</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            tenant    = st.text_input("Tenant name", placeholder="acme_corp", key="wd_tenant")
            client_id = st.text_input("Client ID", key="wd_client_id")
        with col2:
            client_secret = st.text_input("Client secret", type="password", key="wd_secret")
            refresh_token = st.text_input("Refresh token", type="password", key="wd_refresh")

        use_raas = st.checkbox("Use Custom Report (RaaS) instead of REST workers endpoint", key="wd_raas")
        raas_name = ""
        if use_raas:
            raas_name = st.text_input("Report name", placeholder=f"{_brand_name()}_Worker_Extract", key="wd_raas_name",
                                       help="Report name configured by your Workday admin")

        st.caption("Credentials are masked and exist only in this browser session.")

        col_test, col_fetch = st.columns(2)
        with col_test:
            if st.button("Test connection", key="wd_test"):
                if not all([tenant, client_id, client_secret, refresh_token]):
                    st.warning("Fill in all credential fields first.")
                else:
                    with st.spinner("Authenticating…"):
                        conn = WorkdayConnector(tenant, client_id, client_secret, refresh_token)
                        ok, msg = conn.test_connection()
                    st.success(f"✓ Connected to Workday tenant {tenant}") if ok else st.error(f"Failed: {msg}")

        with col_fetch:
            if st.button("Fetch workers", type="primary", key="wd_fetch"):
                if not all([tenant, client_id, client_secret, refresh_token]):
                    st.warning("Fill in all credential fields first.")
                else:
                    with st.spinner("Fetching workers…"):
                        try:
                            conn = WorkdayConnector(tenant, client_id, client_secret, refresh_token)
                            df = (conn.fetch_workers_raas(raas_name) if use_raas and raas_name
                                  else conn.fetch_workers())
                            if df.empty:
                                st.warning("No data returned. Check credentials and API access.")
                            else:
                                st.session_state["upload_df"]       = df
                                st.session_state["upload_title_col"] = _detect_col(df, ["JobTitle","job_title","businessTitle"])
                                st.session_state["upload_name_col"]  = None
                                st.success(f"✓ Fetched **{len(df)} workers** from Workday. Switch to Matching.")
                                st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                        except Exception as exc:
                            st.error(f"Fetch failed: {exc}")


def _detect_col(df, candidates):
    """Return the first candidate column name found in df."""
    for c in candidates:
        if c in df.columns:
            return c
    return df.columns[0] if len(df.columns) > 0 else ""

#!/usr/bin/env python3
"""
walk_signed_in.py — render every page as a real signed-in user, under a chosen
library credential, and say what broke.

    python tools/walk_signed_in.py --email qa@example --password-file ~/.pw --mode user
    python tools/walk_signed_in.py --email qa@example --password-file ~/.pw --mode secret

This is the walk the LIBRARY_CLIENT cutover asked for: the app driven by
streamlit.testing with a genuine Supabase session in session_state (the same
keys auth_service.sign_in writes), config.LIBRARY_CLIENT forced to `--mode`,
and every navigation entry rendered. A page that raises, or shows a Streamlit
error box, is reported by name. Exit code 1 if anything did.

The publishable key is used to sign in, exactly as the browser would; the
secret key is never read by this script.
"""
from __future__ import annotations
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.chdir(HERE)

PAGES = ["Matching", "Connect", "Skills Dashboard", "Skills Assessment", "Skill Gap", "Job Family",
         "Pay Equity", "Benefits Benchmarking", "9-Box Grid", "Architecture Report", "Data Quality",
         "Organisation", "Organigram"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--password-file", required=True)
    ap.add_argument("--mode", choices=["user", "secret"], default="user")
    ap.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args()
    password = open(os.path.expanduser(a.password_file), encoding="utf-8").read().strip()

    import core.config as cfg
    cfg.LIBRARY_CLIENT = a.mode

    import tomllib
    from supabase import create_client
    from streamlit.testing.v1 import AppTest
    secrets = tomllib.load(open(os.path.join(HERE, ".streamlit", "secrets.toml"), "rb"))
    client = create_client(secrets["SUPABASE_URL"], secrets["SUPABASE_PUBLISHABLE_KEY"])
    res = client.auth.sign_in_with_password({"email": a.email, "password": password})
    if not res.session or not res.user:
        print("sign-in failed"); return 2
    orgs = client.table("memberships").select("org_id").execute().data or []
    if not orgs:
        print("account has no membership"); return 2

    at = AppTest.from_file("ui/app.py", default_timeout=a.timeout)
    at.session_state["_auth_client"] = client
    at.session_state["_auth_user"] = {"id": str(res.user.id), "email": res.user.email}
    at.session_state["_auth_active_org"] = orgs[0]["org_id"]
    at.session_state["_auth_signed_in_at"] = time.time()
    at.session_state["_auth_last_seen"] = time.time()
    at.run()

    failures = []
    for page in PAGES:
        try:
            radio = at.sidebar.radio[0]
            radio.set_value(page).run()
            problems = [str(e.value)[:200] for e in at.exception] + [str(e.value)[:200] for e in at.error]
            if problems:
                failures.append((page, problems))
                print(f"FAIL  {page}: {problems[0]}")
            else:
                print(f"ok    {page}")
        except Exception as exc:  # noqa: BLE001 — the point is to report, not to stop
            failures.append((page, [repr(exc)[:200]]))
            print(f"FAIL  {page}: {exc!r}"[:240])

    mode_line = f"mode={a.mode}, signed in as {res.user.email}, org {orgs[0]['org_id'][:8]}"
    print(f"\n{len(PAGES) - len(failures)}/{len(PAGES)} pages rendered clean ({mode_line})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

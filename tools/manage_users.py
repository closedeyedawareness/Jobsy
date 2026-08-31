#!/usr/bin/env python3
"""
manage_users.py — register clients and people, by hand, on purpose.

Jobsy is sold B2B: contracts are invoiced, and access is granted to named
addresses a client has asked for. There is no sign-up page and no self-service
subscription, so this script is the ONLY way an account or a grant comes into
existence. That is a deliberate property, not a missing feature.

    # one-time, per reseller and per client company
    python tools/manage_users.py add-partner --slug acme --name "Acme Consulting"
    python tools/manage_users.py add-client  --slug northwind --name "Northwind BV" --partner acme

    # the addresses the client asked for
    python tools/manage_users.py add-user --email hr@northwind.example
    python tools/manage_users.py grant --email hr@northwind.example --client northwind --role client_admin

    # the reseller's own consultants: one grant, every client they have
    python tools/manage_users.py grant --email you@acme.example --partner acme --role partner_admin

    python tools/manage_users.py list-users
    python tools/manage_users.py revoke --email hr@northwind.example --client northwind

THIS SCRIPT USES THE SECRET KEY, AND IS THE ONLY THING LEFT THAT SHOULD.

The web app runs as the signed-in user so that migration 0008's policies apply
to it. Creating a user and granting a membership are administrative acts that no
browser session may perform — there is no insert policy on `memberships` at all,
by design — so they happen here, from a machine you control, with a key the app
never sees. Keep SUPABASE_SECRET_KEY out of .streamlit/secrets.toml; this script
reads it from the environment only.
"""
from __future__ import annotations

import argparse
import os
import secrets
import string
import sys

ROLES_PARTNER = ("partner_admin", "partner_analyst")
ROLES_CLIENT = ("client_admin", "analyst", "viewer")


def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        die("set SUPABASE_URL and SUPABASE_SECRET_KEY in the environment.\n"
            "  The secret key is an admin credential: do not put it in secrets.toml,\n"
            "  do not commit it, and do not paste it into the app's configuration.")
    if not (key.startswith("sb_secret_") or key.startswith("eyJ")):
        die("that does not look like a secret key. The publishable key cannot create users.")
    try:
        from supabase import create_client
    except ImportError:
        die("pip install -r requirements.txt")
    return create_client(url, key)


def new_password() -> str:
    """A password to hand over out of band, once. Long enough that it does not
    need to be rotated before the person first signs in, though they should
    change it anyway."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(20))


def find_user(sb, email: str):
    """Supabase has no get-user-by-email, so page the admin list."""
    page = 1
    while True:
        users = sb.auth.admin.list_users(page=page, per_page=200)
        if not users:
            return None
        for u in users:
            if (u.email or "").lower() == email.lower():
                return u
        if len(users) < 200:
            return None
        page += 1


def one(sb, table: str, column: str, value: str, what: str):
    rows = sb.table(table).select("*").eq(column, value).limit(1).execute().data or []
    if not rows:
        die(f"no {what} with {column} '{value}'. Run list-{what}s to see what exists.")
    return rows[0]


# ── Commands ──────────────────────────────────────────────────────────────
def cmd_add_partner(sb, a):
    sb.table("partners").insert({"slug": a.slug, "name": a.name}).execute()
    print(f"partner '{a.slug}' created — {a.name}")


def cmd_add_client(sb, a):
    partner = one(sb, "partners", "slug", a.partner, "partner")
    sb.table("orgs").insert({"slug": a.slug, "name": a.name, "partner_id": partner["id"]}).execute()
    print(f"client '{a.slug}' created — {a.name}, under {partner['name']}")


def cmd_add_user(sb, a):
    if find_user(sb, a.email):
        die(f"{a.email} already has an account. Use grant to give it access to a client.")

    if a.invite:
        # Needs working SMTP on the project; the built-in sender is rate-limited
        # and not intended for production.
        sb.auth.admin.invite_user_by_email(a.email)
        print(f"invite sent to {a.email}")
    else:
        password = new_password()
        sb.auth.admin.create_user({
            "email": a.email,
            "password": password,
            "email_confirm": True,   # an operator vouched for this address
            # The app refuses to render anything until this is cleared. The
            # password below gets read down a phone or pasted into a chat, so it
            # exists outside the system from the moment it is issued.
            "user_metadata": {"must_change_password": True},
        })
        print(f"account created for {a.email}")
        print()
        print(f"    temporary password:  {password}")
        print()
        print("Hand that over through a channel that is not email. Jobsy will")
        print("require them to replace it before showing them anything, so it")
        print("only has to survive one sign-in. It is shown once and not stored here.")

    audit(sb, "account.created", None, a.email, {"invited": bool(a.invite)})
    print(f"\n{a.email} cannot reach anything yet — grant them a client next:")
    print(f"    python tools/manage_users.py grant --email {a.email} --client <slug> --role viewer")


def audit(sb, action: str, org_id=None, subject: str = None, detail: dict = None):
    """Record an administrative act.

    D-2: invites, grants and revocations are the actions that widen access, so
    they belong in the trail more than routine reads do. auth.uid() is null here
    -- this runs with the secret key, not as a signed-in user -- so the row is
    attributed to the operator by the detail rather than to a person, which is
    honest about what actually happened: somebody with the admin credential did
    this from a shell.
    """
    try:
        sb.rpc("log_activity", {
            "p_action": action, "p_org": org_id,
            "p_subject": subject, "p_detail": {"via": "manage_users.py", **(detail or {})},
        }).execute()
    except Exception as exc:
        print(f"warning: the action succeeded but was not logged: {exc}", file=sys.stderr)


def cmd_grant(sb, a):
    if bool(a.client) == bool(a.partner):
        die("give exactly one of --client or --partner.\n"
            "  --client  one company. --partner  every client that reseller has.")
    user = find_user(sb, a.email)
    if not user:
        die(f"no account for {a.email}. Run add-user first — this script never creates one implicitly.")

    if a.partner:
        if a.role not in ROLES_PARTNER:
            die(f"--partner takes one of {', '.join(ROLES_PARTNER)} (got '{a.role}').")
        partner = one(sb, "partners", "slug", a.partner, "partner")
        sb.table("memberships").insert({
            "user_id": str(user.id), "partner_id": partner["id"], "role": a.role}).execute()
        n = len(sb.table("orgs").select("id").eq("partner_id", partner["id"]).execute().data or [])
        audit(sb, "membership.grant", None, a.email,
              {"scope": "partner", "partner": a.partner, "role": a.role})
        print(f"{a.email} is now {a.role} at {partner['name']} — reaching {n} client(s)")
    else:
        if a.role not in ROLES_CLIENT:
            die(f"--client takes one of {', '.join(ROLES_CLIENT)} (got '{a.role}').")
        org = one(sb, "orgs", "slug", a.client, "client")
        sb.table("memberships").insert({
            "user_id": str(user.id), "org_id": org["id"], "role": a.role}).execute()
        audit(sb, "membership.grant", org["id"], a.email,
              {"scope": "client", "client": a.client, "role": a.role})
        print(f"{a.email} is now {a.role} at {org['name']}")


def cmd_revoke(sb, a):
    user = find_user(sb, a.email)
    if not user:
        die(f"no account for {a.email}.")
    q = sb.table("memberships").delete().eq("user_id", str(user.id))
    if a.client:
        q = q.eq("org_id", one(sb, "orgs", "slug", a.client, "client")["id"])
    elif a.partner:
        q = q.eq("partner_id", one(sb, "partners", "slug", a.partner, "partner")["id"])
    else:
        die("give --client, --partner, or --all to remove every grant.")
    removed = len(q.execute().data or [])
    audit(sb, "membership.revoke", None, a.email,
          {"client": a.client, "partner": a.partner, "removed": removed})
    print(f"{removed} grant(s) removed from {a.email}")
    print("Effective immediately: access is read from memberships on every query,")
    print("not from a claim baked into their token.")


def cmd_suspend(sb, a):
    """Lock an account without deleting it.

    Deleting the user would be tidier and worse: activity_log keeps the email
    rather than a foreign key precisely so history survives, but there is no
    reason to destroy the account itself while an incident is being looked at.
    A suspension is reversible; a deletion is a decision made under time
    pressure that cannot be walked back.
    """
    user = find_user(sb, a.email)
    if not user:
        die(f"no account for {a.email}.")
    sb.auth.admin.update_user_by_id(str(user.id), {"ban_duration": "876000h"})  # 100 years
    audit(sb, "account.suspended", None, a.email)
    print(f"{a.email} is suspended. Their grants are untouched — reinstate restores access.")
    print("To remove access permanently instead, use revoke --all.")


def cmd_reinstate(sb, a):
    user = find_user(sb, a.email)
    if not user:
        die(f"no account for {a.email}.")
    sb.auth.admin.update_user_by_id(str(user.id), {"ban_duration": "none"})
    audit(sb, "account.reinstated", None, a.email)
    print(f"{a.email} can sign in again.")


def cmd_log(sb, a):
    """Read the trail. Nobody can write to it, including this script -- rows
    arrive only through triggers and app.log()."""
    q = sb.table("activity_log").select("at, actor, action, subject, org_id") \
          .order("at", desc=True).limit(a.limit)
    if a.client:
        q = q.eq("org_id", one(sb, "orgs", "slug", a.client, "client")["id"])
    if a.action:
        q = q.eq("action", a.action)
    rows = q.execute().data or []
    if not rows:
        print("nothing recorded yet.")
        return
    for r in rows:
        print(f"{r['at'][:19]}  {(r.get('actor') or '—'):<32} {r['action']:<26} {r.get('subject') or ''}")


def cmd_retention(sb, a):
    """Set or show how long a client's saved sessions live.

    This is a contract term, so it is read off the DPA rather than guessed. The
    365-day default in 0010 is a placeholder chosen for annual comparability,
    not an answer.
    """
    org = one(sb, "orgs", "slug", a.client, "client")
    if a.days is None:
        print(f"{org['name']}: {org['retention_days']} days")
        return
    sb.table("orgs").update({"retention_days": a.days}).eq("id", org["id"]).execute()
    audit(sb, "retention.changed", org["id"], org["slug"],
          {"from": org["retention_days"], "to": a.days})
    print(f"{org['name']}: sessions now kept {a.days} days after last use "
          f"(was {org['retention_days']})")


def cmd_minimise(sb, a):
    """Turn name pseudonymisation on or off for a client.

    On: the application replaces names with stable tokens before writing a
    session, so the database never holds them. The analyst's screen is
    unaffected. Off: names are stored as uploaded.
    """
    org = one(sb, "orgs", "slug", a.client, "client")
    want = not a.off
    sb.table("orgs").update({"pseudonymise_names": want}).eq("id", org["id"]).execute()
    audit(sb, "minimisation.changed", org["id"], org["slug"], {"pseudonymise_names": want})
    print(f"{org['name']}: names are {'pseudonymised' if want else 'stored as uploaded'}")
    if want:
        print("Sessions saved BEFORE now still hold the names they were saved with.")
        print("Re-save them, or purge them, if that matters.")


def cmd_purge(sb, a):
    """Delete data. Two modes, and neither is reachable from a browser.

    --due     everything past its client's retention period
    --client  everything for one client, for the end of a contract
    """
    if bool(a.due) == bool(a.client):
        die("give exactly one of --due or --client <slug>.")

    if a.due:
        due = sb.rpc("expired_sessions", {}).execute().data or []
        if not due:
            print("nothing is past its retention period.")
            return
        for r in due:
            print(f"  {r['org_name']:<24} {r['session_code']:<18} "
                  f"{r['days_over']} day(s) over a {r['retention_days']}-day limit")
        if not a.yes:
            print(f"\n{len(due)} session(s) would be deleted. Re-run with --yes to proceed.")
            return
        n = sb.rpc("purge_expired_sessions", {}).execute().data
        print(f"{n} expired session(s) deleted.")
        print("Each deletion is in the activity trail; see `manage_users.py log --action jobsy_sessions.delete`.")
        return

    org = one(sb, "orgs", "slug", a.client, "client")
    if not a.yes:
        print(f"About to delete ALL saved sessions and employee records for {org['name']}.")
        print("The client, their memberships and the activity trail are kept.")
        print("This cannot be undone. Re-run with --yes to proceed.")
        return
    result = sb.rpc("purge_client", {"p_org": org["id"]}).execute().data
    print(f"{org['name']}: {result}")
    print("Recorded in the activity trail, which survives even if the client is later removed.")


def cmd_list_users(sb, a):
    rows = sb.table("memberships").select(
        "role, user_id, orgs(name, slug), partners(name, slug)").execute().data or []
    by_user: dict[str, list[str]] = {}
    for r in rows:
        where = (r.get("orgs") or {}).get("name") or f"ALL of {(r.get('partners') or {}).get('name')}"
        by_user.setdefault(r["user_id"], []).append(f"{r['role']} @ {where}")

    page, seen = 1, 0
    while True:
        users = sb.auth.admin.list_users(page=page, per_page=200)
        if not users:
            break
        for u in users:
            seen += 1
            grants = by_user.get(str(u.id), [])
            print(f"{u.email}")
            for g in grants or ["(no access granted)"]:
                print(f"    {g}")
        if len(users) < 200:
            break
        page += 1
    if not seen:
        print("no accounts yet.")


def cmd_list_clients(sb, a):
    for o in sb.table("orgs").select("slug, name, is_library_source, partners(name)")\
                             .order("slug").execute().data or []:
        tag = "  [shared library]" if o.get("is_library_source") else ""
        partner = (o.get("partners") or {}).get("name", "—")
        print(f"{o['slug']:<20} {o['name']:<28} {partner}{tag}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add-partner", help="register a white-label reseller")
    p.add_argument("--slug", required=True); p.add_argument("--name", required=True)
    p.set_defaults(fn=cmd_add_partner)

    p = sub.add_parser("add-client", help="register an end-client company")
    p.add_argument("--slug", required=True); p.add_argument("--name", required=True)
    p.add_argument("--partner", required=True, help="slug of the reseller it belongs to")
    p.set_defaults(fn=cmd_add_client)

    p = sub.add_parser("add-user", help="create an account for an address the client asked for")
    p.add_argument("--email", required=True)
    p.add_argument("--invite", action="store_true",
                   help="email an invite instead of printing a temporary password (needs SMTP)")
    p.set_defaults(fn=cmd_add_user)

    p = sub.add_parser("grant", help="give an existing account access to a client or a whole partner")
    p.add_argument("--email", required=True)
    p.add_argument("--client"); p.add_argument("--partner")
    p.add_argument("--role", required=True,
                   help=f"client: {'|'.join(ROLES_CLIENT)}   partner: {'|'.join(ROLES_PARTNER)}")
    p.set_defaults(fn=cmd_grant)

    p = sub.add_parser("revoke", help="remove access — takes effect on the next query")
    p.add_argument("--email", required=True)
    p.add_argument("--client"); p.add_argument("--partner")
    p.add_argument("--all", action="store_true", help="remove every grant this account has")
    p.set_defaults(fn=cmd_revoke)

    p = sub.add_parser("suspend", help="lock an account, keeping its grants and its history")
    p.add_argument("--email", required=True); p.set_defaults(fn=cmd_suspend)

    p = sub.add_parser("reinstate", help="undo a suspension")
    p.add_argument("--email", required=True); p.set_defaults(fn=cmd_reinstate)

    p = sub.add_parser("log", help="read the activity trail")
    p.add_argument("--client"); p.add_argument("--action")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(fn=cmd_log)

    p = sub.add_parser("retention", help="show or set how long a client's sessions live")
    p.add_argument("--client", required=True)
    p.add_argument("--days", type=int, help="omit to show the current value")
    p.set_defaults(fn=cmd_retention)

    p = sub.add_parser("minimise", help="pseudonymise employee names before storing them")
    p.add_argument("--client", required=True)
    p.add_argument("--off", action="store_true", help="turn it back off")
    p.set_defaults(fn=cmd_minimise)

    p = sub.add_parser("purge", help="delete expired sessions, or everything for one client")
    p.add_argument("--due", action="store_true", help="everything past its retention period")
    p.add_argument("--client", help="everything for this client (end of contract)")
    p.add_argument("--yes", action="store_true", help="required to actually delete")
    p.set_defaults(fn=cmd_purge)

    sub.add_parser("list-users", help="every account and what it can reach").set_defaults(fn=cmd_list_users)
    sub.add_parser("list-clients", help="every client company").set_defaults(fn=cmd_list_clients)

    args = ap.parse_args()
    args.fn(client(), args)


if __name__ == "__main__":
    main()

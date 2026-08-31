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
        })
        print(f"account created for {a.email}")
        print()
        print(f"    temporary password:  {password}")
        print()
        print("Hand that over through a channel that is not email, and have them")
        print("change it after first sign-in. It is shown once and not stored here.")

    print(f"\n{a.email} cannot reach anything yet — grant them a client next:")
    print(f"    python tools/manage_users.py grant --email {a.email} --client <slug> --role viewer")


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
        print(f"{a.email} is now {a.role} at {partner['name']} — reaching {n} client(s)")
    else:
        if a.role not in ROLES_CLIENT:
            die(f"--client takes one of {', '.join(ROLES_CLIENT)} (got '{a.role}').")
        org = one(sb, "orgs", "slug", a.client, "client")
        sb.table("memberships").insert({
            "user_id": str(user.id), "org_id": org["id"], "role": a.role}).execute()
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
    print(f"{removed} grant(s) removed from {a.email}")
    print("Effective immediately: access is read from memberships on every query,")
    print("not from a claim baked into their token.")


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

    sub.add_parser("list-users", help="every account and what it can reach").set_defaults(fn=cmd_list_users)
    sub.add_parser("list-clients", help="every client company").set_defaults(fn=cmd_list_clients)

    args = ap.parse_args()
    args.fn(client(), args)


if __name__ == "__main__":
    main()

# Cutover: turning the fence on

Applying `0007`–`0013` to the live project (`qpprcmmdeqlbursogosu`) and moving the
app off the secret key.

**This is one deployment, not seven.** `0008` and the key swap have to land in the same
window. `0008`'s own header says why:

> policies without the key change — written, never exercised, believed
> key change without the policies — every query denied, app dead

Owner: Elmar · Rehearsed: 2026-09-01 · Est. 30 min including verification

---

## What was verified before writing this

Not assumed — measured, read-only, against the live project.

| Check | Result |
|---|---|
| Migrations applied on live | `0001`–`0006` only (six rows in the migration table) |
| Live schema vs. a fresh local `0001`–`0006` | **identical** — md5 `a00a8f5d1f63143b4df58fe2f1460534`, 386 columns both sides |
| `0007`–`0013` applied to that exact structure, with rows present | all seven **APPLIED**, no errors |
| Personal data on live | **none** — `employees` 0 rows, no `jobsy_sessions` table yet |
| Library on live | 1 org (`default`), 81 jobs, 45 bands, 325 title mappings, 1008 benefit observations |
| Current RLS posture | RLS **enabled on all 25 tables, zero policies** — everything is denied, and the app works only because it holds the secret key, which bypasses RLS |
| `anon` grants | `0008`'s hand-maintained revoke list was two tables short (`pay_mix`, `pay_elements`). Not exploitable — RLS returned 0 rows — but the second layer was missing. `0013` revokes from the catalogue instead of a list |

Zero drift is the important one: it means the migrations will do on live exactly what
they did in rehearsal, and what the 237-assertion suite exercises.

**Nothing has been applied to live.** Every command below is yours to run.

---

## Before you start

- [ ] Take a backup / confirm PITR is on. There is no personal data to lose, but the
      library is 1,600-odd rows of real work.
- [ ] Have `SUPABASE_SECRET_KEY` available in your shell (**not** in
      `.streamlit/secrets.toml` — `manage_users.py` reads it from the environment only).
- [ ] Know where the deployed app's secrets live, because step 3 edits them.
- [ ] Pick a quiet window. Between steps 2 and 3 the app is degraded.

---

## Step 1 — apply the migrations, in order

```
0007_partners_users_and_membership.sql
0008_rls_policies.sql
0009_least_privilege_and_activity_log.sql
0010_retention_and_minimisation.sql
0011_partner_branding.sql
0012_country_dimension.sql
0013_anon_reaches_nothing.sql
```

Order matters: `0007` creates `partners` and `memberships`, and everything after
depends on them.

They are self-configuring. After they run you should already have, with no manual
step: `orgs.is_library_source = true` on `default`, a partner row with
`orgs.partner_id` pointing at it, `default_country = 'NL'`, `retention_days = 365`,
`pseudonymise_names = false`, 10 seeded countries, and 49 policies.

**Verify before continuing:**

```sql
\i supabase/verify_cutover.sql
```

Every line must say `ok`. If any says `CHECK`, stop — do not do step 3.

## Step 2 — create the first accounts

**Do this before the key swap.** After step 3 the app obeys `memberships`, and
immediately after migration that table is **empty** — so nobody can reach anything,
including you. `manage_users.py` uses the secret key and bypasses RLS, so it works
either side of the swap, but doing it first means the app is never unusable.

```bash
export SUPABASE_SECRET_KEY=...

python tools/manage_users.py add-partner --slug <reseller> --name "<Reseller>"
python tools/manage_users.py add-client  --slug <client> --name "<Client BV>" --partner <reseller>
python tools/manage_users.py add-user    --email you@example.com
python tools/manage_users.py grant --email you@example.com --partner <reseller> --role partner_admin
python tools/manage_users.py list-users
```

Do **not** grant anyone against the `default` org. It is the library, not a client.

## Step 3 — the key swap (the irreversible half)

In the deployed app's secrets, replace:

```toml
SUPABASE_KEY = "<secret / service_role key>"
```

with:

```toml
SUPABASE_URL = "https://qpprcmmdeqlbursogosu.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "<publishable / anon key>"
```

`auth_service.py` refuses to start if it detects a secret key here, so a mistake
fails loudly rather than silently leaving RLS bypassed.

Restart the app.

## Step 4 — close the front door

In the Supabase dashboard:

- [ ] **Authentication → Sign-Ups: OFF.** Jobsy is sold B2B on invoice; there is no
      self-service subscription, and an open sign-up page contradicts that.
- [ ] **Authentication → Providers: disable every OAuth provider.**

Neither is enforced by a migration, so neither is covered by the test suite. They
are the two settings that can quietly undo the whole model.

## Step 5 — prove it from a browser

Not from SQL. SQL proves the policies; only a browser proves the *application* asks
the right questions — that distinction has already caught one real defect here.

- [ ] Signed out, you get a sign-in form and no application content behind it.
- [ ] A wrong password is refused without revealing whether the address exists.
- [ ] You sign in and see your client, and only your client.
- [ ] A second client's session code, pasted into "Load session code", gets you
      nothing.
- [ ] A `viewer` account sees no Save button.

`tests/e2e/journey.py` runs exactly these against a local stack.

---

## If it goes wrong

**Everything denied, app dead after step 3.** Almost certainly zero memberships, or
a grant against `default` instead of a client org. Check with
`select * from memberships;` using the secret key. Fix with `manage_users.py grant`.
No rollback needed.

**You need to get back to a working app immediately.** Put the secret key back in
the app's secrets and restart. The migrations can stay — with the service key the
app bypasses RLS and behaves as it does today. This is a real escape hatch, but it
puts you back in the posture where the fence exists and is not exercised, so treat
it as an incident, not a resting state.

**A migration itself failed.** It should not — all seven were rehearsed against a
byte-identical schema — but each is written to be re-runnable
(`if not exists` / `add_constraint_if_absent`), so fix the cause and re-run the
same file.

---

## What this does *not* give you

Worth being straight about before anyone repeats it to a client:

- **The sign-in page cannot be partner-branded.** Before sign-in there is no
  identity, so there is no partner to look up, and resolving one from the URL would
  let an anonymous visitor enumerate your resellers. See `0011`.
- **No SSO and no MFA.** Fine for a lite NL product; not yet enough for a
  multinational's security review.
- **The 365-day retention is a placeholder**, not a number the partner has agreed.
  When they give you one it is an `UPDATE`, not a migration.
- **Nobody has run a real client's roster through this yet.** Every assurance above
  comes from synthetic data.

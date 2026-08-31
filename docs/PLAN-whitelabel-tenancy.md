# Implementation Plan — White-Label Tenancy, Auth and Client Isolation

**Trigger:** Jobsy may be resold white-label by a large multinational as part of their services.
**Goal:** Give Jobsy real logins and a real fence between clients, **without rewriting the app.**
Status: **Stages 1-4 done (`0007`-`0009`, 128 SQL assertions + 4 CI guards green) — Stage 5 next** · Owner: Eng

**Supabase project `Jobsy` — ref `qpprcmmdeqlbursogosu`** (eu-central-1, org `nubdeiwupcofidifrbfn`,
Pro plan). The older free-tier `Jobsy` (`ocornnoqosxjwxubrcgk`, org "People Harmonics") is a dead
project pending auto-pause and is **not** what this plan targets — see E-2.

**Commercial model, which decides half the auth design.** Jobsy is sold B2B: contracts are
invoiced, and access is granted to named addresses a client asks for. There is **no self-service
sign-up, no social login, and no subscription flow** — accounts are registered by an operator through
`tools/manage_users.py`. This removes work rather than adding it: no email-verification flow, no
account-recovery abuse surface, no OAuth provider to review. It also means one setting has to be
right in the Supabase dashboard, because no code can enforce it: **Authentication → Sign-Ups →
"Allow new users to sign up" OFF**, and every OAuth provider disabled.

The domain logic is not in scope. ~17k lines of matching, pay-equity regression, benefits
benchmarking and reporting stay as they are. What is missing is the layer underneath: Jobsy has no
concept of a user and no concept of a client.

---

## 0. Checked against the code, 2026-08-31

Read from `main`, not inferred. Every claim below cites the line it came from.

| Control | What the code does | Consequence |
|---|---|---|
| Authentication | One shared password from Streamlit secrets, compared `pw != expected` — `ui/app.py:2957–2982` | No user identity exists. Nobody can be individually granted, revoked or attributed. |
| Tenancy | `org_label` is a free-text caption stored beside the payload — `ui/app.py:3033` | Nothing scopes a query. Two clients are distinguished by a label, not a boundary. |
| Isolation | `?session=CODE` auto-loads a session on page open — `ui/app.py:3007–3016` | The code is the only barrier, and it travels in URLs, history and referrers. |
| Code strength | `random.choices` over 5 chars of A–Z0–9 — `services/persistence_service.py:198` | Not a cryptographic generator; 36⁵ ≈ 60M keyspace, no rate limit. |
| Row-level security | Enabled on every table, zero policies; app connects with the **secret** key — `SUPABASE_SETUP.sql:60–75` | RLS is inert. The connection reaches every row of every client. |
| Client lifetime | `_client` / `_status_cache` are module-level globals — `services/persistence_service.py:38–39` | Streamlit shares one process across all browsers. See B-4. |
| Audit | Append-only trail, correctly hardened, but only for the reference library — `supabase/migrations/0003` | Changes to shared content are traceable. Access to client data is not. |
| Data in scope | Employee id, name, title, salary, gender, birth/start date — `services/pay_equity_service.py:10, 330` | Personal data under GDPR, processed to produce a gender pay-gap analysis. |

Two things this repo already got right, and this plan builds on rather than replaces:

- **The RLS gap is deliberate and documented.** `0005_lock_down_functions.sql` records it as finding
  3: *"Until auth lands there is no org claim to filter on, and a permissive policy written now is a
  hole nobody remembers to close."* This plan is auth landing. The advisor's INFO severity was the
  right reading of a deliberate choice; it stops being right the moment a second client exists.
- **`Employees` was called out from the start.** `PLAN-supabase-migration.md` §0: *"the table that
  will hold personal data and therefore the one where RLS stops being theoretical."* It is no longer
  theoretical.

### 0.1 Corrections, after building Stage 1

Two claims in the first draft of this plan were wrong. Both were wrong in the same direction — the
schema was in better shape than the app was — and both were found by reading the migrations properly
rather than by reading `ui/app.py` and generalising.

- **"No table models a partner or a client" was half wrong.** `orgs` has existed since `0001`, and
  `org_id uuid not null references orgs(id)` is threaded through **all 20** reference tables, each
  with its own index and composite unique constraints. `0001` says why: *"retrofitting a tenant key
  onto populated tables with live foreign keys is the kind of migration that goes wrong; carrying an
  unused column is cheap by comparison. Enforcement arrives with auth (Phase 0.3)."* That decision,
  taken before there was any reason for it, is why Stage 1 was a day's work instead of a fortnight's.
  What was genuinely missing was the level *above* a client (partners) and the level *below* it
  (memberships) — plus a tenant key on the one table that holds actual rosters.

- **The rosters are not in this database.** `jobsy_sessions` does not exist in project
  `qpprcmmdeqlbursogosu` at all — `SUPABASE_SETUP.sql` instructs an operator to run it by hand in the
  SQL editor, and nobody ever did. Verified 2026-08-31:

  | table | rows |
  |---|---|
  | `orgs` | 1 (the seeded default) |
  | `jobs` | 81 |
  | `salary_bands` | 45 |
  | `library_audit` | 10,468 |
  | `employees` | 0 |
  | `auth.users` | 0 |
  | `jobsy_sessions` | **table absent** |

  So **there is no personal data in this database**, and the fence is being built before anything
  lands behind it rather than after. That is the comfortable order, and it will not come round again.

  It also means session persistence has never worked against this project: `save_session()` returns
  `False` and the UI reports "Save failed." That is unchanged by `0007` — the table now exists but
  requires an `org_id` the app cannot yet supply, because it does not know who is using it. Stage 2
  is what makes saving work, and it is the first time it ever will against this project.

One correction to an assumption in the current code, worth recording because the comment is
confident and load-bearing:

- **`SUPABASE_SETUP.sql` argues the secret key is safe "because Jobsy is server-rendered Streamlit",
  and that is true only of *exposure*.** The key never reaches a browser, which is what that comment
  claims. But the same key is also what makes RLS inert, so the reasoning that protects it from
  leaking is unrelated to the reasoning that would protect one client's data from another's session.
  Single-tenant, this distinction did not matter. It is the whole problem multi-tenant.

---

## 1. Shape of the thing being built

The partner resells to their own clients, and those clients will not administer the database — they
need a fence they can be shown, and logins for their people. That is one database with the boundary
enforced in Postgres, not a project per client.

**Three levels.** A **partner** owns the white-label instance. A partner has many **clients** — the
end companies whose rosters are analysed. A **user** reaches a client through a **membership**
carrying a role. Partner staff hold memberships across many clients; a client's own staff hold one.

Every row of client data carries a `client_id`, and every policy asks one question: *does the person
making this request hold a membership for this row's client?*

**Enforced in the database, not the app.** A policy applies to every query, including the one
somebody forgets to filter. That is only true once the connection carries the user's token — while
the app holds the secret key, the fence is decorative. This is why B-3 gates everything else.

**The Streamlit-shaped hazard.** Streamlit serves every browser session from one Python process, and
`_client` is a module-level global (`persistence_service.py:38`). Attach a user's token to that
global and it becomes shared state: whoever logged in most recently supplies the identity for
everybody. The client must be built per session and held in `st.session_state`. B-7's isolation test
should be written with two users active at once, because that is the only way this failure shows up.

---

## 2. Requirements register

No security questionnaire has arrived from the client, so this list is written forward: what a
multinational's security, procurement and data-protection functions normally require of a processor
handling HR compensation data. **Replace with theirs when it arrives.**

IDs are stable so an item can be deferred or signed off by name. **P0** means the answer to a
standard security question is today "no", in a way that stops the sale.

### A — Identity and access

| ID | Requirement | Today | Pri |
|---|---|---|---|
| A-1 | Named user accounts | **Done in Stage 2** — Supabase Auth, invite-only, `services/auth_service.py` | P0 |
| A-2 | Individual provisioning and same-day revocation | **Done** — `manage_users.py` add/grant/revoke/suspend/reinstate, plus forced password rotation on first sign-in | P0 |
| A-3 | Roles, least privilege | **Done in `0009`** — read / edit / admin, enforced in Postgres. Fixes a real gap `0008` shipped, see §3.3 | P0 |
| A-4 | Session expiry and logout | **Done** — 1h idle, 12h absolute, explicit sign-out | P0 |
| A-5 | Constant-time credential comparison | **Moot** — the app no longer compares a password at all; Supabase Auth does | P0 |
| A-6 | MFA for admin roles | None | P1 |
| A-7 | SSO (SAML/OIDC) | None | P1 |

### B — Tenancy and isolation

| ID | Requirement | Today | Pri |
|---|---|---|---|
| B-1 | Three-level tenancy in the schema | ~~No table models a partner or a client~~ — **wrong, see §0.1**. `orgs` and `org_id` existed already; partner + membership did not. **Done in `0007`** | P0 |
| B-2 | RLS policies on every table carrying client data | **Done in `0008`** — 45 policies | P0 |
| B-3 | User traffic stops using the secret key | **Done** — publishable key + user token; a CI guard fails if the secret key is read | P0 |
| B-4 | Per-session DB client, never a module global | **Done** — client in `st.session_state`; `tests/test_tenancy_invariants.py` fails if a global returns | P0 |
| B-5 | Session codes unguessable, and no longer the access control | **Done** — `secrets`, 31^10, and membership decides access | P0 |
| B-6 | No client identifiers in URLs | **Done** — auto-load removed, code stripped from the query string | P1 |
| B-7 | Automated test proving isolation | **Done** — `supabase/tests/0008_rls_isolation_test.sql`, real users behind the `authenticated` role | P0 |

### C — Privacy and data protection

| ID | Requirement | Today | Pri |
|---|---|---|---|
| C-1 | Processor agreement and sub-processor register | Nothing written | P0 |
| C-2 | Records of processing (Art. 30) and a DPIA | Nothing written. Salary × gender at scale triggers one | P0 |
| C-3 | Retention, deletion, end-of-contract purge | Sessions stored indefinitely; no delete path | P0 |
| C-4 | Data minimisation / pseudonymisation | Full names captured into the payload; analytics don't need them | P1 |
| C-5 | EU data residency | `eu-central-1`. Confirm the app host too | P1 |
| C-6 | Encryption in transit and at rest | Platform-provided, undocumented | P1 |
| C-7 | Breach detection and 72-hour notification | No process, and no logging to characterise one | P1 |

### D — Audit and evidence

| ID | Requirement | Today | Pri |
|---|---|---|---|
| D-1 | Access log for client data | **Done in `0009`** — `activity_log`. Writes by trigger; reads and exports logged by the app, which is the honest limit | P0 |
| D-2 | Administrative actions logged | **Done** — grants, revocations, suspensions and account creation, from `manage_users.py` | P0 |
| D-3 | Tamper evidence on the trail | **Done** — no write grant for anon, authenticated **or service_role**; no write policy; rows arrive only via definer functions | P1 |
| D-4 | Export log | **Partial** — `public.log_activity()` exists and session opens are logged; each export button still needs wiring | P1 |

### E — Operations

| ID | Requirement | Today | Pri |
|---|---|---|---|
| E-1 | Backups, and a restore that has been tested | Pro plan implies daily; PITR is a separate add-on. **Verify**, then rehearse once | P1 |
| E-2 | Separate production and staging | Two Jobsy databases exist; retire the free-tier one deliberately | P1 |
| E-3 | Availability commitment | No SLA possible on current app hosting | P1 |
| E-4 | Vulnerability and dependency management | Advisor used and acted on (`0005`); not yet a standing process | P2 |
| E-5 | Independent penetration test | None. Schedule after B lands, before their review | P2 |

### F — White-label mechanics

| ID | Requirement | Today | Pri |
|---|---|---|---|
| F-1 | Per-partner branding | People Harmonics palette hard-coded in `.streamlit/config.toml` | P1 |
| F-2 | "Jobsy" fully removable | Page title, auth screen, and the `JOBSY-` code prefix | P1 |
| F-3 | Per-client reference data | Library is DB-backed already, but shared by everyone | P2 |
| F-4 | Usage metering per client | None. Cheap now, awkward to retrofit | P2 |

**Totals:** 25 absent · 6 partial · 1 in place · 2 to verify · **16 blocking (P0)**

---

## 3. Order of work

Sequenced so each stage is independently demonstrable and the sale-blocking items land first.

| Stage | What lands | Covers |
|---|---|---|
| 1 ✅ | **Tenancy schema.** Partners, clients, memberships, roles. `client_id` on every table holding client data, backfilled. No behaviour change — this is the vocabulary everything else needs. | B-1 |
| 2 ✅ | **Real logins.** Supabase Auth replaces the shared password. Per-session client carrying the user's token; session expiry; sign-out. Secret key retired from every user-facing path. | A-1, A-4, A-5, B-3, B-4 |
| 3 ✅ | **The fence, and the proof of it.** RLS policies on every table, plus the two-user test that fails to cross. Session codes regenerated cryptographically and demoted to convenience. | B-2, B-5, B-6, B-7 |
| 4 ✅ | **Roles, administration, trail.** Invite, suspend, remove. Role enforcement in UI and database. Access and admin logging on the `0003` append-only pattern. | A-2, A-3, D-1…D-4 |
| 5 | **Retention and minimisation.** Per-client purge, session expiry, pseudonymised names at ingest — what makes a deletion clause true rather than aspirational. | C-3, C-4 |
| 6 | **White-label surface.** Per-partner name, logo, palette; every hard-coded "Jobsy" behind config. | F-1, F-2 |
| 7 | **Enterprise readiness.** SSO, MFA, the documentation pack, external pen test. | A-6, A-7, C-1, C-2, C-6, E-3, E-5 |

---

## 3.1 Stage 1 — done

`supabase/migrations/0007_partners_users_and_membership.sql`. No behaviour change; no policy written.

- **`partners`**, and `orgs.partner_id` not-null, backfilled to a seeded `default` partner exactly as
  `0001` seeded a `default` org.
- **`memberships`**, scoped to *either* a partner *or* a client, never both. Partner staff get one
  row that reaches every client the partner has — because a consultant with forty clients otherwise
  needs forty rows kept in step, and the row somebody forgets to delete is the one that matters.
  Roles are constrained to the scope that can hold them, so "partner_admin on one client" and
  "viewer across an entire partner" are unrepresentable rather than discouraged.
- **`app.member_org_ids()` / `app.can_access_org()` / `app.is_org_admin()`** — what `0008`'s policies
  will ask. Three deliberate choices, each one an existing lesson from this repo applied:
  - `SECURITY DEFINER`, because `memberships` gets RLS in `0008` and a policy that reads it would be
    filtered by its own policy — infinite recursion, reported as a stack-depth error far from the
    cause.
  - **a private `app` schema**, because `0005` had to revoke execute on `log_library_change()` after
    PostgREST published it at `/rest/v1/rpc/`. Every function in `public` is an API endpoint by
    default; `app` is not served over HTTP but is perfectly callable from inside a policy.
  - **pinned `search_path`**, the same finding `0005` fixed on two other functions.
- **`jobsy_sessions`**, created with `org_id` from birth, superseding the hand-run
  `SUPABASE_SETUP.sql`. A table the app depends on belongs in the migration series rather than in a
  manual step that can be skipped — which is demonstrably what happened.

**Verified by attack, not by reading the DDL back** — `./supabase/tests/run.sh` stands up a
throwaway Postgres, applies all seven migrations and runs 40 assertions. **40 passed, 0 failed.**

| Attempted write | Result |
|---|---|
| Membership scoped to both a partner and an org | rejected (check) |
| Membership scoped to neither | rejected (check) |
| `partner_admin` granted at client scope | rejected (check) |
| `viewer` granted across a whole partner | rejected (check) |
| An invented role | rejected (check) |
| Second membership for the same user + org | rejected (partial unique) |
| Second membership for the same user + partner | rejected (partial unique) |
| Membership for a user that does not exist | rejected (foreign key) |
| An org with no partner | rejected (not null) |
| A session with no org | rejected (not null) |
| A session pointing at a non-existent org | rejected (foreign key) |
| Duplicate `session_code` across two different orgs | rejected (unique) |
| A legitimate session, and a second in another org | accepted — the constraints are not over-tight |

And the access questions, which are the ones the fence turns on:

| Who | Sees | Blocked from |
|---|---|---|
| Acme consultant (`partner_admin`) | both Acme clients | Initech — **different partner** |
| Northwind HR (`client_admin`) | Northwind only | Contoso — **same partner, different client** |
| Initech viewer | Initech, admins nothing | — |
| User with no membership | nothing | everything |
| Anonymous (no JWT) | nothing | everything |

This is **not** B-7 yet. It proves the membership logic; B-7 needs the same two users to collide
through *RLS on live tables*, which cannot exist until `0008`. The test file is where that goes.

---

## 3.2 Stages 2 and 3 — done, together

They had to ship together. `0007`'s own header says why: a policy without the key change is written,
never exercised, and believed; the key change without a policy is every query denied and a dead app.

**`0008_rls_policies.sql`** — 45 policies. Client data (`employees`, `jobsy_sessions`) is
membership-only with no exemption. Reference tables use a read/write split, because of a problem a
naive rule creates:

> **The shared library problem.** "You see rows for orgs you belong to" breaks the product on day
> one. The reference library — 81 jobs, the salary bands, the CAO crosswalk — lives in the `default`
> org that `0001` seeded. It is not any client's data; it is the thing being sold. A membership-only
> rule shows a new client an empty library and a broken app. So an org can be flagged
> `is_library_source`: its reference rows are readable by any signed-in user and writable only by the
> importer. Per-client libraries (F-3) later become "library source for one partner only" — the flag
> is where that goes, and nothing else moves.

Both `using` and `with check` are set everywhere. `using` alone would let a member of client A insert
a row *stamped* client B, which is the direction people forget.

**`services/auth_service.py`** — sign-in, sign-out, expiry, client switching. No `sign_up()`, no
OAuth, no path from an unknown address to an account. The client is built per browser session and
kept in `st.session_state`; there is no module-level client, and `tests/test_tenancy_invariants.py`
fails the build if one comes back.

**`services/persistence_service.py`** — rewritten. No module global, no secret key, `org_id` required
on write, and `generate_code()` moved from `random.choices` over 36⁵ to `secrets` over 31¹⁰. The code
is no longer the access control, so that is the belt to a pair of braces.

**`tools/manage_users.py`** — the only way an account or a grant exists. Runs with the secret key,
which now has exactly one legitimate home outside the importer. There is deliberately **no insert
policy on `memberships`**: the API cannot create a grant at all, from any session, at any role.

**`ui/app.py`** — the shared-password gate is gone, replaced by sign-in plus a client switcher that
clears the previous client's data out of session state on every switch. `?session=` auto-load
removed and the code stripped from the query string (B-6).

### Verified

`./supabase/tests/run.sh` — **87 assertions, 0 failed**, against a throwaway Postgres running the
whole migration series. `0008_rls_isolation_test.sql` is B-7: real users behind the `authenticated`
role with a real JWT subject, querying the tables directly, so what is under test is the policies as
the database applies them rather than a helper the app could forget to call.

| Attempt | Result |
|---|---|
| Client HR reads a **sibling client under the same partner** | invisible |
| Client HR reads **another partner's** client | invisible |
| Client HR inserts a roster **stamped with the sibling's org id** | blocked by `with check` |
| Client HR **moves** their own roster into the sibling client | blocked |
| Client HR edits or adds to the **shared library** | blocked |
| Consultant reads **both** their partner's clients | allowed |
| Consultant writes to a **rival partner's** client | blocked |
| Viewer writes anything | blocked |
| A viewer **grants themselves** another client | blocked |
| Even a `client_admin` creates a membership from the app | blocked — no insert policy exists |
| `anon` reads any table | permission denied at the grant level, before RLS |
| Signed in, but no membership | sees nothing |

Plus four CI guards in `tests/test_tenancy_invariants.py` that need no database: no module-level DB
client, no `sign_up`/OAuth call, no reading of the secret key, and session codes from `secrets` over
an unambiguous alphabet. Each was checked by reintroducing the defect and confirming the test fails.

### Two things this found

- **An identity-less token could read the shared library.** `can_read_org()` returned true for
  library orgs without checking `auth.uid()`. Not personal data, but it is the product being resold.
  The test asserted the correct behaviour before the code had it.
- **`insert ... select ... from orgs where slug='victim'` is not an attack.** The attacker cannot see
  the victim's org, so the subquery returns nothing, zero rows are written, and psql reports success.
  The first version of the isolation test was green for that reason. Org ids are now captured as
  superuser and interpolated as literals, and writes are judged on rows affected — "no exception" is
  not "denied".

### Not done, and deliberately

- **Forced password rotation on first sign-in.** `manage_users.py` prints a temporary password to
  hand over out of band. Rotation belongs with the rest of A-2 in Stage 4.
- **The two dashboard settings** no code can enforce: sign-ups OFF, OAuth providers disabled.
- **`0008` is not applied to the live database.** It is applied and attacked locally on every run of
  `run.sh`. Applying it to production is a deployment decision, and it must land in the same change
  as the app — see the top of this section.

---

## 3.3 Stage 4 — done, and it started by fixing Stage 3

**`0008` shipped a defect, and `0009` opens by fixing it.** The policy was:

```sql
create policy jobsy_sessions_isolation on jobsy_sessions for all
  using (app.can_access_org(org_id))
```

`for all` with a membership-only test means **every member can write** — including a `viewer`, the
one role whose entire purpose is to be read-only. Same on `employees`. Demonstrated before writing
the fix, not deduced:

```
set role authenticated;
select set_config('request.jwt.claim.sub', '<a viewer>', false);
insert into jobsy_sessions (org_id, session_code) select id, 'VIEWER-WRITE-TEST' ...
-- INSERT 0 1
```

`0008`'s own test *did* check a viewer against reference data and correctly found it blocked — that
path goes through `can_write_org()`, which requires admin. It never tried a viewer against **client**
data, so the gap sat precisely where the test was not looking. The lesson is not "write more tests";
it is that **a role is not tested until it has been tried against every table it can reach.**

### Three levels of permission, not two

| | Function | Who |
|---|---|---|
| read | `can_access_org()` | any member — viewers stop here |
| edit | `can_edit_org()` | analysts and admins — rosters, employees |
| admin | `is_org_admin()` | admins only — reference data, the audit trail |

### The trail

`activity_log` records who touched whose client data. Writes to `jobsy_sessions` and `employees` are
recorded **by trigger**, so they cannot be forgotten. Reads and exports are recorded by the app,
because a `SELECT` fires no trigger — that is a real limit of D-1 and is stated rather than glossed.

Three deliberate choices:

- **`actor_id` is not a foreign key to `auth.users`, and the email is copied in.** Deleting a user
  must not delete or blank the record of what they did. An audit trail that a `delete from
  auth.users` can edit is not evidence of anything. Tested: the history survives the user.
- **The roster payload is stripped from the log.** Copying names, salaries and gender into a second
  table on every save would double the personal data held, in a table nobody can delete from, for no
  investigative gain. "Who changed this, and when" is answered without it.
- **`service_role` cannot write, update, delete or truncate it either.** That is the credential
  `manage_users.py` and the importer hold, and it bypasses RLS — so leaving it able to `DELETE` would
  mean the one key an operator holds could erase the record of an operator's own actions. Rows still
  arrive: the trigger and `app.log()` are `SECURITY DEFINER` and run as the owner.

### One door into the private schema

`app.*` is not served over HTTP, which is why it exists. But the app must record reads. So exactly
one wrapper is exposed — `public.log_activity()` — which calls straight through and adds no
capability: the actor still comes from `auth.uid()` rather than an argument, and the org is checked
against membership. Moving `app.log()` into `public` would have been simpler and would also have
published `member_org_ids()`, `is_org_admin()` and `can_edit_org()` as REST endpoints.

### What the tests found this time

**`0005`'s finding, reintroduced by me.** `0005` revoked `execute` on `log_library_change()` after
finding PostgREST had published it at `/rest/v1/rpc/`, calling it *"precisely the wrong function to
leave callable"*. `log_client_data_change()` is the same kind of function and arrived with the same
default grant to `PUBLIC`. It was caught immediately — by `0007`'s own assertion that **no** `app`
function is executable by `anon`, which had been written as a property rather than a count and so
failed the moment a new migration broke it. Revoked, and the triggers were then verified still to
fire rather than assumed to.

### Verified

`./supabase/tests/run.sh` — **128 assertions, 0 failed.** New in `0009_privilege_and_audit_test.sql`:

| Attempt | Result |
|---|---|
| A **viewer** inserts / updates / deletes a roster in their own client | blocked (was allowed before `0009`) |
| A **viewer** inserts or deletes an employee | blocked |
| An **analyst** writes a roster and an employee | allowed |
| An **analyst** edits reference data | blocked — admin only |
| An **analyst** reads the audit trail | sees nothing |
| A **client_admin** deletes, rewrites or forges a log row | blocked |
| **`service_role`** deletes, truncates or rewrites the trail | blocked; may still read |
| `log_activity()` against a client you cannot reach | blocked |
| Deleting the user | history survives, email still readable |

### Not done

- **Wiring every export button** to `log_activity()`. The mechanism and the session-open call are in;
  each export path still needs its line (D-4).
- **A trail viewer in the app.** `manage_users.py log` reads it from a shell today.

---

## 4. Open — the partner has to answer these

Each changes the build, so they belong in the next conversation rather than the last one.

- **Who is the controller?** If the end-client controls and the partner processes, Jobsy is a
  sub-processor — which decides whose paperwork gets signed and who must approve us.
- **Their identity provider.** Entra ID, Okta, something else. Sets what A-7 actually means.
- **Do the end-clients' own staff log in, or only partner consultants?** Decides how much of
  section A is needed at launch.
- **Retention period.** How long may a roster live after an engagement ends? C-3 needs a number.
- **Uptime and support terms in the partner's contract.** Decide whether the app can stay on its
  current hosting (E-3).
- **Billing model.** Per client, per seat, per employee analysed. Cheap to build into the schema in
  stage 1, awkward afterwards (F-4).

# End-to-end: drive Jobsy in a browser as four different people

`supabase/tests/*.sql` prove the policies. They cannot prove that the
*application* asks the right questions — and it did not. This suite caught a
real defect the SQL tests were structurally unable to see, described at the
bottom.

## What is real here, and what is not

Being precise about this matters: a test that quietly fakes the thing under test
is worse than no test.

| | |
|---|---|
| **real** | PostgreSQL 16, migrations `0001`–`0011` applied verbatim |
| **real** | PostgREST 12.2.3, the official binary — resource embedding, filters and upserts behave exactly as against Supabase |
| **real** | Row-level security. Every request carries a signed JWT; PostgREST sets `role=authenticated` and the claims; the policies decide what comes back |
| **real** | The Jobsy application, unmodified |
| **real** | Chromium driving the actual UI |
| **stubbed** | Token minting and password checking (GoTrue), ~60 lines in `supabase_shim.py` |

The stub is the part **not** under test. What is being tested is whether a
signed-in user can reach another client's data, and that is decided by Postgres.

## Running it

Needs a local PostgreSQL, the PostgREST binary, and Playwright's Chromium.

```bash
# 1. a database with the migrations and some fixtures
createdb jobsy_e2e
psql -d jobsy_e2e -f supabase/tests/_supabase_stub.sql
for f in supabase/migrations/*.sql; do psql -d jobsy_e2e -f "$f"; done
psql -d jobsy_e2e -f tests/e2e/fixtures.sql

# 2. the API layer
postgrest tests/e2e/postgrest.conf &
python tests/e2e/supabase_shim.py &          # prints ANON_KEY=...

# 3. point the app at it, in .streamlit/secrets.toml
#      SUPABASE_URL = "http://127.0.0.1:8001"
#      SUPABASE_PUBLISHABLE_KEY = "<the ANON_KEY it printed>"
streamlit run ui/app.py --server.port 8599 --server.headless true &

# 4. drive it
python tests/e2e/journey.py
```

## What it covers

Signed out; a wrong password; a client admin; a partner consultant across two
clients; a read-only viewer; a new starter on a temporary password. Twenty-two
assertions about what each of them can and cannot see.

## The defect it found

`accessible_orgs()` selected from `memberships` **without filtering to the
signed-in user**, relying on RLS to scope it. But `memberships_read` (0009)
deliberately lets an org admin read other people's membership rows — they have
to, to administer their client. So the browser showed a `partner_admin`
consultant the label **"Northwind BV · client admin"**: somebody else's role.

No data leaked, and the database was never the weak point. But the UI derived
"what am I on this client" from whatever RLS happened to return, and the SQL
tests could not catch it because at the database level nothing was wrong. It
took a browser and two people with different roles on the same client.

## Two harness bugs, also worth recording

Both made a test pass while proving nothing, which is the failure mode that
matters most in a suite like this.

- A Streamlit `text_input` commits on blur or Enter, not on `fill()`. The
  "open somebody else's session code" test typed into the void and asserted
  against a page that had never been asked the question.
- A Streamlit `selectbox` renders only the *selected* option until it is opened,
  so reading the page text proved nothing about what the switcher offered.

"""Jobsy core configuration."""
# The country a deployment defaults to when nothing else says otherwise. It is
# a DEFAULT, not a fact: migration 0012 puts a country on every priced reference
# row, on each client (orgs.default_country) and on each employee, because the
# customers Jobsy is sold to have staff in several. Anything that reads this
# constant is answering "what should I assume", never "where is this person
# paid" -- ask the row for that.
#
# ROADMAP 3.1. Adding a market is: import rows carrying its code, then flip
# is_live in the countries table.
DEFAULT_COUNTRY   = "NL"
COUNTRY           = DEFAULT_COUNTRY   # kept: ui/app.py reads it for the badge

# Currency follows the country, not the deployment -- countries.currency is the
# source of truth. This is only the fallback for a display before any country is
# known, and PLN/SEK/DKK exist in that table precisely so nothing assumes euro.
DEFAULT_CURRENCY  = "EUR"
DEFAULT_THRESHOLD = 85
WORKBOOK_PATH     = "jobsy_reference_library.xlsx"

# Where the reference library is read from: "excel" | "db".
#
# The database is the master as of 2026-07-28, when tests/test_library_parity.py
# passed 10/10 against the seeded library: frames, statistics and whole records
# identical to the workbook, with one documented difference (governance Status
# is lowercase in the database by design). Catalog swaps its loader and nothing
# else changes, because Repository only ever sees a dict of DataFrames.
#
# Rolling back is setting this to "excel" again. The committed workbook stays a
# working master either way, and db_loader falls back to it — loudly, via
# Catalog.fell_back_to_excel and a sidebar warning — if the database is
# unreachable. Reading a stale file silently is the failure this migration
# exists to end, so the fallback is never quiet.
LIBRARY_SOURCE    = "db"

# Whose rows the DB loader reads. One tenant today; org_id has been on every
# table since migration 0001, so Phase 0.3 is a policy change rather than a
# migration onto populated tables.
LIBRARY_ORG_SLUG  = "default"

# WHICH CREDENTIAL the DB loader reads the library with: "secret" | "user".
#
# "secret" is how it has always worked and is still the default: the app holds
# the project's secret key, which bypasses row-level security entirely. That was
# fine when Jobsy had one tenant and a shared password. It stopped being fine
# when PR #32 gave it named accounts and 0008's policies, because every page now
# runs with a credential those policies do not apply to — the half of the
# tenancy work that is not true yet.
#
# "user" reads the library through the signed-in user's own client, so the
# policies decide what comes back. Flipping this is the whole cutover, the same
# way LIBRARY_SOURCE was: one line, and one line back.
#
# Before flipping it, two things must hold, and both are tested:
#   - the reference tables have a read policy for `authenticated` keyed on org
#     membership (0008, plus 0014 for the two pay tables it missed), and
#   - that policy depends on the ORG ONLY, never on the member's role — the
#     catalog is cached per org and shared between that org's sessions.
LIBRARY_CLIENT    = "secret"

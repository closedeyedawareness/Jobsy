"""Jobsy core configuration."""

# The country the app opens in. It is a default, not a boundary: since migration
# 0007 the reference library is split into a global spine and a per-country
# market layer, and core/countries.py is the source of truth for which markets
# exist and which of them have data. This name is kept because several modules
# import it; new code should ask core.countries.
COUNTRY           = "NL"
DEFAULT_COUNTRY   = COUNTRY
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

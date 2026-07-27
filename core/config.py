"""Jobsy core configuration."""
COUNTRY           = "NL"
DEFAULT_THRESHOLD = 85
WORKBOOK_PATH     = "jobsy_reference_library.xlsx"

# Where the reference library is read from: "excel" | "db".
#
# Still "excel" while W5's parity test is what decides. Flipping this IS the
# cutover — Catalog swaps its loader and nothing else changes, because
# Repository only ever sees a dict of DataFrames. Rolling back is setting it to
# "excel" again; the committed workbook stays a working master either way.
LIBRARY_SOURCE    = "excel"

# Whose rows the DB loader reads. One tenant today; org_id has been on every
# table since migration 0001, so Phase 0.3 is a policy change rather than a
# migration onto populated tables.
LIBRARY_ORG_SLUG  = "default"

"""
tests/test_sheet_map_coverage.py

One invariant, deliberately in its own file: every sheet the app loads is
either compared against the database or excluded on purpose.

It lived in tests/test_library_parity.py, which is right on subject and wrong
on gating. That module skips entirely without SUPABASE_URL and a secret key —
correct for every test in it that compares a real workbook against a real
database, and fatal for this one, which compares two dictionaries and needs
nothing at all.

The cost was demonstrated on 6 September 2026. Migration 0016's two split-out
tables were added to SHEET_MAP, and this guard — written precisely to catch a
sheet the app loads and nothing checks — was skipped along with the rest of its
module and said nothing. A guard that only runs where the thing it guards is
already known to be fine is not a guard.
"""
from __future__ import annotations

from core.catalog import SHEET_MAP
from tests.test_library_parity import _COMPARISON_KEYS, NOT_COMPARED


def test_every_loaded_sheet_is_either_compared_or_excluded_on_purpose():
    """The same silence that let PayMix and PayElements sit outside the library
    for two months: loaded by the app, checked by nothing."""
    uncovered = set(SHEET_MAP.values()) - set(_COMPARISON_KEYS) - set(NOT_COMPARED)
    assert not uncovered, (
        "these sheets are loaded by the app and neither compared nor excluded "
        "on purpose: " + ", ".join(sorted(uncovered))
        + " — add a sort key to _COMPARISON_KEYS, or a reason to NOT_COMPARED")


def test_the_guard_itself_runs_without_credentials():
    """The point of the move, asserted so it cannot quietly be undone.

    If somebody adds a module-level skipif here — or moves this test back
    beside the comparison — the guard stops running in the ordinary suite and
    the next sheet slips through the same way.
    """
    import tests.test_sheet_map_coverage as me
    assert not hasattr(me, "pytestmark"), (
        "this module has grown a pytestmark; the guard must run unconditionally")

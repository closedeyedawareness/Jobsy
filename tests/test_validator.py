"""tests/test_validator.py"""

import pandas as pd
import pytest

from core.exceptions import ValidationError
from core.validator import Validator


def test_clean_data_passes(sample_sheets):
    report = Validator().validate(sample_sheets, strict=False)
    assert report.ok
    assert report.errors == []


def test_missing_sheet_is_error(sample_sheets):
    del sample_sheets["salary"]
    report = Validator().validate(sample_sheets, strict=False)
    assert not report.ok
    assert any("salary" in e for e in report.errors)


def test_missing_required_column_is_error(sample_sheets):
    sample_sheets["jobs"] = sample_sheets["jobs"].drop(columns=["StandardTitle"])
    report = Validator().validate(sample_sheets, strict=False)
    assert not report.ok
    assert any("StandardTitle" in e for e in report.errors)


def test_empty_jobs_is_error(sample_sheets):
    sample_sheets["jobs"] = sample_sheets["jobs"].iloc[0:0]
    report = Validator().validate(sample_sheets, strict=False)
    assert any("empty" in e.lower() for e in report.errors)


def test_duplicate_job_ids_is_error(sample_sheets):
    dup = sample_sheets["jobs"].iloc[[0]]
    sample_sheets["jobs"] = pd.concat([sample_sheets["jobs"], dup], ignore_index=True)
    report = Validator().validate(sample_sheets, strict=False)
    assert any("Duplicate" in e for e in report.errors)


def test_salary_min_over_max_is_warning(sample_sheets):
    s = sample_sheets["salary"].copy()
    s.loc[0, "Min"] = 999999
    sample_sheets["salary"] = s
    report = Validator().validate(sample_sheets, strict=False)
    assert report.ok  # warning, not error
    assert any("min" in w.lower() and "max" in w.lower() for w in report.warnings)


def test_unknown_reference_is_warning(sample_sheets):
    extra = pd.DataFrame([{"JobID": "J-GHOST", "Description": "x"}])
    sample_sheets["profiles"] = pd.concat([sample_sheets["profiles"], extra], ignore_index=True)
    report = Validator().validate(sample_sheets, strict=False)
    assert any("J-GHOST" in w for w in report.warnings)


def test_strict_raises_on_error(sample_sheets):
    del sample_sheets["jobs"]
    with pytest.raises(ValidationError):
        Validator().validate(sample_sheets, strict=True)


def test_benefits_sheets_are_optional(sample_sheets):
    # sample_sheets has no benefits keys at all — must not be flagged as missing.
    report = Validator().validate(sample_sheets, strict=False)
    assert report.ok
    assert not any("benefit" in e.lower() for e in report.errors)


def test_benefits_missing_column_is_error_only_when_sheet_present(sample_sheets):
    sample_sheets["benefitscatalog"] = pd.DataFrame([{"NotCategory": "Wellness"}])
    report = Validator().validate(sample_sheets, strict=False)
    assert not report.ok
    assert any("benefitscatalog" in e and "Category" in e for e in report.errors)


def test_unknown_benefit_industry_reference_is_warning(sample_sheets):
    sample_sheets["industries"] = pd.DataFrame([{"IndustryID": "IND-TECH"}])
    sample_sheets["benefitsobservations"] = pd.DataFrame([
        {"IndustryID": "IND-GHOST", "Category": "Wellness", "Value": 100},
    ])
    report = Validator().validate(sample_sheets, strict=False)
    assert report.ok  # warning, not error
    assert any("IND-GHOST" in w for w in report.warnings)

#!/usr/bin/env python3
"""
build_rating_sheet.py — assemble the evidence a rater needs, and nothing else.

    python projects/art4-job-evaluation/tools/build_rating_sheet.py

Regenerates scoring/reference-roles-scoring.csv from the live library: one row
per reference role, every piece of evidence the library holds for each of the
four factors, and four EMPTY rating columns.

WHY THERE IS NO PROPOSED DEGREE COLUMN

It would be easy to derive a skills degree from `skills_max_required_level` and
save the rater some work. Two reasons not to.

The first is that they are different quantities. Required level is how deep the
job must go in one named skill, on a 1-5 competency scale. The skills factor
degree is what command of a DOMAIN the job requires, on a 1-6 scale anchored in
qualification and expertise language. Mapping one onto the other because both
are small integers is the same mistake as looking our own grade points up in
ISF's published table: two scales, same units, different meaning.

The second is anchoring. A proposed degree sitting next to an empty box is not
a neutral starting point — raters move toward it, and the resulting instrument
would encode a rule nobody chose while looking like human judgement.

So the evidence is assembled and the judgement is left. Effort and working
conditions get no evidence columns at all, because the library holds none: a
white-collar reference set never needed them. That emptiness is honest and it is
also the size of the work.
"""
from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

from core.catalog import Catalog  # noqa: E402

OUT = ROOT / "projects" / "art4-job-evaluation" / "scoring" / "reference-roles-scoring.csv"

COLUMNS = [
    "job_id", "standard_title", "function", "level",
    # ── skills evidence ──
    "skills_evidence", "skills_max_required_level", "skills_n_core", "skills_n_leadership",
    "esco_label",
    # ── responsibility evidence ──
    # management_level is a POSITIONING claim against a national grading
    # instrument (0016 §1), so the market it was read for travels beside it.
    # An Art. 4 evidence sheet that cannot say which ladder a rung belongs to
    # is evidence nobody can check in 2028.
    "management_level", "positioning_country", "key_responsibilities",
    "grade_autonomy", "grade_span_of_control", "grade_decision_rights", "grade_authority",
    # ── effort evidence: none exists ──
    # ── working conditions evidence: none exists ──
    "description",
    # ── the judgement, left blank on purpose ──
    "RATE_skills_degree_1to6", "RATE_effort_degree_1to6",
    "RATE_responsibility_degree_1to6", "RATE_working_conditions_degree_1to6",
    "rating_notes",
]


def build() -> list[dict]:
    repo = Catalog(str(ROOT / "jobsy_reference_library.xlsx"), source="excel").load().repository
    # Which market's positioning this sheet is built from. Asked once, named in
    # every row: 0016 moved management_level to a table keyed by country, and
    # the resolver answers country then the EU baseline then NOTHING — so a
    # blank management_level below means "this market makes no such claim", not
    # "the library is thin".
    from services import country_service
    try:
        market = (country_service.active_country() or "NL").strip().upper()
    except Exception:
        market = "NL"
    rows = []
    for job in sorted(repo.jobs.values(), key=lambda j: (j.function or "", j.grade or 0)):
        reqs = repo.role_skill_map.get(job.job_id, [])
        profile = repo.profiles.get(job.job_id)
        grade = repo.job_grades.get(job.grade)
        names = []
        for r in reqs:
            sk = repo.skills.get(r.skill_id)
            if sk:
                names.append(f"{sk.skill_name} L{r.required_level}/{r.skill_type}")
        rows.append({
            "job_id": job.job_id, "standard_title": job.standard_title,
            "function": job.function, "level": job.level,
            "skills_evidence": "; ".join(names),
            "skills_max_required_level": max((r.required_level for r in reqs), default=""),
            "skills_n_core": sum(1 for r in reqs if r.skill_type == "Core"),
            "skills_n_leadership": sum(1 for r in reqs if r.skill_type == "Leadership"),
            "esco_label": job.esco_label,
            # Read through the repository, not off the profile: the field there is
            # a snapshot taken when the library was built, and this accessor is
            # the one that resolves the market at the moment it is asked.
            "management_level": repo.management_level_for(job.job_id),
            "positioning_country": market,
            "key_responsibilities": "; ".join(getattr(profile, "key_responsibilities", ()) or ())
                                    if profile else "",
            "grade_autonomy": getattr(grade, "autonomy", "") if grade else "",
            "grade_span_of_control": getattr(grade, "span_of_control", "") if grade else "",
            "grade_decision_rights": getattr(grade, "decision_rights", "") if grade else "",
            "grade_authority": getattr(grade, "authority", "") if grade else "",
            "description": (getattr(profile, "description", "") or "")[:400] if profile else "",
            "RATE_skills_degree_1to6": "", "RATE_effort_degree_1to6": "",
            "RATE_responsibility_degree_1to6": "", "RATE_working_conditions_degree_1to6": "",
            "rating_notes": "",
        })
    return rows


def main() -> int:
    rows = build()
    # THE CURRENT GRADE IS NOT IN THIS FILE. It lives in the reconciliation sheet
    # and enters only after scoring — see the circularity guard in the README.
    assert not any("grade" == k for k in COLUMNS), "the grade must not reach the scoring sheet"
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    filled = sum(1 for r in rows if r["grade_autonomy"])
    print(f"{len(rows)} roles written to {OUT.relative_to(ROOT).as_posix()}")
    print(f"  responsibility evidence from the grade ladder on {filled} of {len(rows)}")
    print(f"  effort evidence: none — the library holds none")
    print(f"  working conditions evidence: none — the library holds none")
    print(f"  ratings left blank: {len(rows) * 4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

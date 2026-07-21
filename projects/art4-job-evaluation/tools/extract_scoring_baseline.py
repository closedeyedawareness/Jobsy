"""
projects/art4-job-evaluation/tools/extract_scoring_baseline.py

Regenerates scoring/reference-roles-scoring.csv from the live reference
library: one row per role, pre-populated with every piece of evidence the
database already holds (skills requirements, management level,
responsibilities, description), with EMPTY rating columns for the four
Art. 4 factors.

Deliberate design (see project README, "circularity guard"):
  * current grade/level are NOT on this sheet -- they go to a separate
    reconciliation file compared only AFTER scoring is complete;
  * effort and working-conditions evidence columns are thin on purpose --
    those factors must be rated, not inferred from data we don't hold.

Run from the repo root:  python projects/art4-job-evaluation/tools/extract_scoring_baseline.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from core.catalog import Catalog  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "scoring"
SCORING_CSV = OUT_DIR / "reference-roles-scoring.csv"
RECON_CSV = OUT_DIR / "reconciliation-baseline.csv"


def main() -> None:
    repo = Catalog(str(REPO_ROOT / "jobsy_reference_library.xlsx")).load().repository
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    scoring_rows = []
    recon_rows = []
    for jid, job in sorted(repo.jobs.items()):
        prof = repo.profiles.get(jid)
        reqs = repo.role_skill_map.get(jid, [])

        skill_evidence = "; ".join(
            f"{repo.skills[r.skill_id].skill_name if r.skill_id in repo.skills else r.skill_id}"
            f" (req {r.required_level}, {r.skill_type})"
            for r in sorted(reqs, key=lambda r: (-r.required_level, r.skill_type))
        )
        max_req = max((r.required_level for r in reqs), default=None)
        n_core = sum(1 for r in reqs if r.skill_type == "Core")
        n_leadership = sum(1 for r in reqs if r.skill_type == "Leadership")

        scoring_rows.append({
            "job_id": jid,
            "standard_title": job.standard_title,
            "function": job.function,
            # -- evidence: Skills --
            "skills_evidence": skill_evidence,
            "skills_max_required_level": max_req,
            "skills_n_core": n_core,
            "skills_n_leadership": n_leadership,
            # -- evidence: Responsibility --
            "management_level": (prof.management_level if prof else "") or "",
            "key_responsibilities": " | ".join(prof.key_responsibilities) if prof else "",
            # -- evidence: general --
            "description": (prof.description if prof else "") or "",
            # -- ratings: TO BE FILLED, degrees per instrument/factor-degrees.md --
            "RATE_skills_degree_1to6": "",
            "RATE_effort_degree_1to6": "",
            "RATE_responsibility_degree_1to6": "",
            "RATE_working_conditions_degree_1to6": "",
            "rating_notes": "",
        })
        recon_rows.append({
            "job_id": jid,
            "standard_title": job.standard_title,
            "current_grade": job.grade,
            "current_level": job.level,
        })

    with SCORING_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(scoring_rows[0].keys()))
        w.writeheader()
        w.writerows(scoring_rows)

    with RECON_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(recon_rows[0].keys()))
        w.writeheader()
        w.writerows(recon_rows)

    print(f"Wrote {len(scoring_rows)} roles -> {SCORING_CSV}")
    print(f"Wrote grade baseline (KEEP OFF THE SCORING SHEET) -> {RECON_CSV}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
rate.py — the rating bench. One role at a time, evidence and degrees together.

    C:\\Jobsy\\.venv\\Scripts\\python.exe -m streamlit run projects/art4-job-evaluation/tools/rate.py

324 judgements is the distance between a scaffold and an instrument, and the
thing that makes it slow is not the deciding — it is hunting for the evidence
and re-reading the degree definitions between roles. So both sit on the screen,
and the only thing asked for is the judgement.

THREE PROPERTIES THAT ARE NOT COSMETIC

**The current grade is not on this screen, and is not in the file.** The
circularity guard: if the ladder is visible while rating, the instrument
measures the ladder. reconcile() compares the two AFTERWARDS, and mismatches
are the finding this whole project exists to produce. Seeing the answer first
would destroy that in a way nothing downstream could detect.

**Nothing is pre-filled.** A suggested degree beside an empty box is not a
neutral head start — raters move toward it, and the result encodes a rule
nobody chose while looking like judgement. Blank is slower and it is the
measurement.

**Every rating can carry a note, and the notes are the audit trail.** Art. 4(4)
requires criteria applied "in an objective gender-neutral manner". When someone
asks in 2028 why this role sits at degree 4, the answer has to be a sentence a
person wrote, not an inference from the number.

Ratings save straight back to scoring/reference-roles-scoring.csv, so the work
survives closing the tab, and rating can stop and resume.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

SHEET = ROOT / "projects" / "art4-job-evaluation" / "scoring" / "reference-roles-scoring.csv"
FACTORS = [
    ("RATE_skills_degree_1to6", "Skills", "kennis en vaardigheden"),
    ("RATE_effort_degree_1to6", "Effort", "inspanning"),
    ("RATE_responsibility_degree_1to6", "Responsibility", "verantwoordelijkheid"),
    ("RATE_working_conditions_degree_1to6", "Working conditions", "arbeidsomstandigheden"),
]

# The degree definitions, so nobody rates from memory. Skills follows the
# REVISED proposal — a search across considerations, not one education line.
DEGREES = {
    "Skills": {
        1: "Learnable on the job in weeks. No qualification or certification required.",
        2: "Routine methods of one domain. Certification, if any, is an entry formality.",
        3: "Full professional command incl. non-routine cases — OR one legally required certification, actively used and maintained.",
        4: "Deep command of one domain — OR certified across several distinct regulated domains — OR a statutory registration with personal accountability and upkeep.",
        5: "Recognised reference point; sets method for others. Where regulated, holds the senior registration and signs what others cannot.",
        6: "Shapes the discipline across the organisation or beyond; where regulated, carries the register's accountability personally.",
    },
    "Effort": {
        1: "Routine attention; interruptions cost little; low emotional demand.",
        2: "Sustained attention in stretches; occasional deadline pressure.",
        3: "Regular deep concentration OR regular emotionally demanding interactions (conflict, distress, high-stakes clients).",
        4: "Frequent complex problem-solving under time pressure OR sustained emotional load as a core feature of the work.",
        5: "Continuous high cognitive load with material consequence of lapses; or intense emotional demand with little recovery.",
        6: "Extreme sustained demand few can carry long-term; the org structures rotation or support around it.",
    },
    "Responsibility": {
        1: "Own task quality; errors caught nearby; no budget, no reports.",
        2: "Own workstream; errors surface downstream at real but recoverable cost; may coordinate informally.",
        3: "Owns a process or project end to end; measurable budget/asset responsibility; may lead 1–5 people.",
        4: "Owns a domain or department outcome; sets priorities within mandate; leads a team OR carries equivalent expert accountability.",
        5: "Owns a function; decisions move organisation-level results; accountable for multiple teams or org-critical assets.",
        6: "Enterprise accountability; decisions bind the organisation externally.",
    },
    "Working conditions": {
        1: "Controlled indoor environment, regular hours, no meaningful hazard.",
        2: "Mostly controlled; occasional travel, occasional evening/weekend peaks.",
        3: "Regular travel OR structurally irregular hours OR regular demanding physical/sensory circumstances.",
        4: "Frequent site/field work with real physical demand or hazard controls; or structural on-call.",
        5: "Predominantly demanding or hazard-managed environments; irregularity shapes private life.",
        6: "Sustained hazardous or extreme conditions as the core context of the job.",
    },
}

REMINDERS = {
    "Skills": "A licence raises the degree only where the WORK requires it — a certificate the "
              "role does not use is a fact about a person, and Art. 4 evaluates the job. "
              "Degrees 3+ must stay reachable on demonstrated command alone.",
    "Effort": "Emotional load is first-class here. Its historic omission is one of the "
              "documented gender-bias failure modes in job evaluation.",
    "Responsibility": "Not readable through headcount alone — 'or equivalent expert "
                      "accountability' exists so senior expert tracks are not undervalued "
                      "against managerial ones.",
    "Working conditions": "Rate the job's NORMAL conditions, not incidents.",
}


def load() -> tuple[list[dict], list[str]]:
    with SHEET.open(encoding="utf-8", newline="") as fh:
        r = csv.DictReader(fh)
        return list(r), list(r.fieldnames or [])


def save(rows: list[dict], cols: list[str]) -> None:
    with SHEET.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    st.set_page_config(page_title="Art. 4 rating bench", layout="wide")
    rows, cols = load()

    assert not any(c.lower() in ("grade", "current_grade") for c in cols), \
        "the current grade must never reach the rating sheet — see the circularity guard"

    done = sum(1 for r in rows if all(r[k] for k, _, _ in FACTORS))
    st.markdown(f"### Art. 4 rating bench &nbsp;·&nbsp; {done} of {len(rows)} roles complete")
    st.progress(done / len(rows) if rows else 0.0)
    st.caption("The current grade is deliberately absent from this screen and from the file. "
               "Rating against it would make the reconciliation measure the ladder instead of "
               "testing it. Nothing is pre-filled, for the same reason.")

    only_todo = st.checkbox("Show only unrated roles", value=True)
    pool = [i for i, r in enumerate(rows)
            if not only_todo or not all(r[k] for k, _, _ in FACTORS)]
    if not pool:
        st.success("Every role is rated. Run the weighting session next — "
                   "separation() will show which factors actually separate anything.")
        return

    labels = [f"{rows[i]['job_id']} — {rows[i]['standard_title']}" for i in pool]
    choice = st.selectbox("Role", range(len(pool)), format_func=lambda k: labels[k])
    idx = pool[choice]
    row = rows[idx]

    left, right = st.columns([3, 2])

    with left:
        st.markdown(f"#### {row['standard_title']}")
        st.caption(f"{row['function']} · {row['level']} · {row['job_id']}"
                   + (f" · ESCO: {row['esco_label']}" if row.get("esco_label") else ""))
        if row.get("description"):
            st.write(row["description"])
        with st.expander("Skills evidence", expanded=True):
            st.caption(f"max required level {row.get('skills_max_required_level') or '—'} · "
                       f"{row.get('skills_n_core') or 0} core · "
                       f"{row.get('skills_n_leadership') or 0} leadership")
            st.write(row.get("skills_evidence") or "—")
            st.info("The library holds no certification or licence data — 0 of 75 skills name "
                    "one. If this role requires a statutory licence, that knowledge is yours, "
                    "not the sheet's. Note it.")
        with st.expander("Responsibility evidence", expanded=True):
            for lab, key in (("Management level", "management_level"),
                             ("Key responsibilities", "key_responsibilities"),
                             ("Autonomy (grade)", "grade_autonomy"),
                             ("Span of control (grade)", "grade_span_of_control"),
                             ("Decision rights (grade)", "grade_decision_rights"),
                             ("Authority (grade)", "grade_authority")):
                if row.get(key):
                    st.markdown(f"**{lab}** — {row[key]}")
        with st.expander("Effort and working conditions evidence"):
            st.warning("None. The reference library never needed either, so there is nothing "
                       "to read here — these two are judgement from the role description and "
                       "what you know of the work. That emptiness is why 162 of the 324 "
                       "ratings cannot be shortcut.")

    with right:
        st.markdown("#### The judgement")
        for key, name, dutch in FACTORS:
            current = row.get(key) or ""
            options = ["—"] + [str(d) for d in range(1, 7)]
            pick = st.radio(
                f"**{name}** · {dutch}", options,
                index=options.index(current) if current in options else 0,
                horizontal=True, key=f"{row['job_id']}_{key}")
            st.caption(REMINDERS[name])
            with st.expander(f"{name} — degree definitions"):
                for d, text in DEGREES[name].items():
                    st.markdown(f"**{d}** — {text}")
            row[key] = "" if pick == "—" else pick
            st.divider()

        row["rating_notes"] = st.text_area(
            "Why these degrees — the audit trail",
            value=row.get("rating_notes") or "",
            placeholder="The sentence someone reads in 2028 when they ask why this role "
                        "sits where it does.",
            key=f"{row['job_id']}_notes")

        if st.button("Save this role", type="primary", use_container_width=True):
            rows[idx] = row
            save(rows, cols)
            st.success(f"{row['job_id']} saved.")
            st.rerun()


main()

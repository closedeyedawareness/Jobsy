# CAO Metalektro — ISF salary-group reference (admin / crosswalk)

**Status:** internal reference for the LKQ / Metalektro enquiry (see the client email, July 2026).
**Purpose:** this is an **admin reference table**, NOT data loaded into Jobsy's grading engine.
Jobsy produces its own independent grade; a **separate crosswalk step** maps that indicative
grade onto the public CAO salary groups below. The official classification stays with a
certified ISF/CATS evaluation — see "IP & honesty boundary" at the bottom.

---

## ✅ Verification status — RESOLVED 2026-07-21

The numbers below were first drafted from an **AI-generated summary** and were NOT fully
verified. Both primary FNV PDFs (public, no login needed — the FME page is member-gated and
couldn't be checked) were fetched and read directly (extracted via PyMuPDF since standard
text extraction failed on both). Every figure below is now sourced to an exact page.

| Item | Status (verified 2026-07-21) |
|---|---|
| Group structure A–K (Basis) + L–Q (Hoger Personeel) | ✅ confirmed |
| HP income threshold **€131.256/yr**, monthly × **12.96** | ✅ confirmed — HP-cao PDF p.8 (art. 3.2.1b/c) |
| A–K point boundaries (0–130, 131–180, … 536–590) | ✅ confirmed exactly as drafted — Basis-cao PDF p.96 |
| 2026 monthly min/max € per scale A–K | ✅ confirmed exactly as drafted — Basis-cao PDF p.16-17 (tabel 3.3.1) |
| Band **L = 591–645**, **M = 646–700** | ✅ confirmed — HP-cao PDF p.7 |
| Bands **N, O, P, Q** | ❌ **the original draft was wrong on all four, not just Q** — corrected below |

**Corrected L–Q table (HP-cao PDF p.7, "Tabel: Groepsgrenzen hoger personeel bij toepassing ISF"):**

| Salarisgroep | Draft had | **Verified (use this)** |
|---|---|---|
| N | 701–755 | **701–760** |
| O | 756–810 | **761–820** |
| P | 811–865 | **821–880** |
| Q | 866+ | **881–940** |

Sources fetched and read directly:
- FME — Salaristabellen cao Metalektro 2026: https://www.fme.nl/salaristabellen-cao-metalektro-2026 (member-gated, could not verify from this — not needed, the two FNV PDFs below cover everything)
- FNV — Basis-cao Metalektro 2026 (PDF, 123 pages): https://www.fnv.nl/getmedia/5d171cbc-1373-43c9-9d71-06fd03042fbf/315-metalektro-cao-01-01-2026-tm-31-12-2026-v09042026.pdf
- FNV — Metalektro Hoger Personeel cao 2026 (PDF, 65 pages): https://www.fnv.nl/getmedia/322d5c42-4596-41fd-885c-a605c31a5f83/2050-metalektro-hoger-personeel-cao-01-01-2026-tm-31-12-2026-v18022026.pdf

---

## 1. Basis-CAO salary groups A–K (ISF point ranges)

| Salarisgroep | ISF puntenbereik |
|---|---|
| A | 0 – 130 |
| B | 131 – 180 |
| C | 181 – 230 |
| D | 231 – 280 |
| E | 281 – 330 |
| F | 331 – 380 |
| G | 381 – 430 |
| H | 431 – 480 |
| J | 481 – 535 |
| K | 536 – 590 |

## 2. Hoger Personeel (HP) salary groups L–Q (ISF point ranges)

Applies above ~590 points, up to the income cap in §4.

| Salarisgroep | ISF puntenbereik |
|---|---|
| L | 591 – 645 |
| M | 646 – 700 |
| N | 701 – 760 |
| O | 761 – 820 |
| P | 821 – 880 |
| Q | 881 – 940 |

## 3. 2026 monthly salary scales A–K (Basis, 38-hr week) — ✅ verified (Basis-cao PDF p.16-17)

Minimum = 0 functiejaren (step 0). Maximum = ceiling after the mandated experience steps.
Amounts exclude the 8% holiday allowance, shift premiums and overtime.

| Scale | 2026 min (step 0) | 2026 max | Steps to max |
|---|---|---|---|
| A | €2.768,86 | €2.803,01 | 1 yr |
| B | €2.809,65 | €2.897,15 | 2 yr |
| C | €2.869,64 | €3.030,46 | 3 yr |
| D | €2.954,58 | €3.195,36 | 4 yr |
| E | €3.057,10 | €3.398,63 | 5 yr |
| F | €3.178,77 | €3.637,77 | 6 yr |
| G | €3.318,71 | €3.922,71 | 7 yr |
| H | €3.487,83 | €4.255,92 | 8 yr |
| J | €3.702,73 | €4.655,03 | 9 yr |
| K | €3.950,20 | €5.121,58 | 10 yr |

*(HP scales L–Q are not rigid monthly step tables; L starts roughly where K ends (~€5.122+/mo)
up to the annual cap below.)*

## 4. Scope cap

- CAO scales apply strictly to employees under **€131.256 gross/year** (2026).
- Test: monthly base × **12.96** (base + holiday allowance) vs the cap.
- Above the cap → **boven-CAO**: the employer may structure pay outside the ISF tables.

---

## 5. CATS® — researched 2026-07-21, and why it can't be crosswalked the same way

CATS® (**C**ommercieel, **A**dministratief, **T**echnisch en **S**ociaal) is owned by De Leeuw
Consult, not FME — a *different* system from ISF, used across many *other* sector CAOs (Metaal
en Techniek, Grafimedia, Recreatiebranche, Woningcorporaties, Mode- en Sportbranche,
Meubelbranche, Timmerfabrieken, Vleesverwerkende Industrie, Architectenbranche,
Vlakglasindustrie, Groothandel — NOT Metalektro, which uses ISF).

Read the public 403-page "Handboek Functie-indeling voor de Metaal en Techniek" (5e editie,
via FNV) as the concrete example. **The key finding: CATS has no public numeric point-boundary
table to crosswalk against, unlike ISF.**

- ISF: a function scores N points (protected method) → a **published table** says "281-330
  points = salarisgroep E." The boundary table itself is public even though the scoring method
  isn't — that's what section 1-2 above crosswalks against.
- CATS: functiegroep numbers map 1:1 to salarisgroep letters (functiegroep 2 = A, 3 = B, ... 11 = J
  for Metaal en Techniek — a *different* CAO has its own mapping), but there is **no published
  point-range table behind that**. Classification happens by comparing a job's content against
  **95 "functiefamilies,"** each with its own qualitative "niveaublad" (level sheet) of
  characteristics per functiegroep, plus worked "referentiefuncties" — a structured but entirely
  *qualitative* comparison process, not a point sum crossed against fixed boundaries.

**Consequence for any Jobsy filter:** the ISF-style "indicative grade → public point-range →
salary group" crosswalk genuinely cannot be built for CATS the same way — the public numeric
structure it would crosswalk against doesn't exist. What CAN be done honestly for a CATS-covered
client: surface Jobsy's own indicative level next to the CAO's functiegroep-to-salarisgroep
label mapping (if that specific sector's CAO is loaded), clearly marked as a label alignment only,
with **no implied point score** — and note that the actual classification still requires reading
the relevant niveaublad, same as ISF requires a certified weging. Also: CATS's mapping is
per-sector (Metaal en Techniek's A-J table won't match Grafimedia's or Woningcorporaties'), so a
CATS crosswalk needs its own reference table *per client CAO*, not one universal table the way
ISF effectively is for Metalektro.

Source read directly: FNV — Handboek Functie-indeling voor de Metaal en Techniek, 5e editie
(403 pages): https://www.fnv.nl/getmedia/f5939ffa-df02-4e1c-8cfe-0d840c20a6a6/529-handboek-functie-indeling-metaal-en-techniek.pdf

---

## IP & honesty boundary (why the crosswalk lives here, not in the engine)

- **Public (safe to hold here):** the group structure, the point-range *boundaries*, the salary
  scales, the income cap. These are published CAO content (algemeen verbindend verklaard).
- **Protected (must NOT be reproduced into Jobsy):** the ISF *scoring method* — the kenmerken
  and how a function is analysed into points. That is FME's IP (ISF); CATS® is De Leeuw Consult's.
  Encoding that into an automated system needs written permission / a licence.
- **Therefore the honest design:** Jobsy shows its **own** indicative grade → maps to an
  **indicative CAO group** → displays the **public scale** for that group. It must **not** print a
  computed "ISF-puntenscore" (a real one needs the protected method; a fake one dressed as ISF
  is the dishonesty we're avoiding). Output reads e.g. *"Indicatief: salarisgroep F —
  officiële ISF/CATS-indeling vereist een gecertificeerde weging."*

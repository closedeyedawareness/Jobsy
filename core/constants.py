LEVELS = ["Junior", "Medior", "Senior", "Lead"]
FUNCTIONS = ["HR", "Finance", "Engineering", "Data", "Product"]


# --- Skills Intelligence: self-declared proficiency → 1–5 CompetencyLevel scale ---
PROFICIENCY_WORD_TO_LEVEL = {
    "none": 1, "awareness": 1, "aware": 1,
    "beginner": 2, "basic": 2, "foundational": 2, "novice": 2,
    "intermediate": 3, "proficient": 3, "competent": 3, "working": 3,
    "advanced": 4, "skilled": 4, "strong": 4,
    "expert": 5, "mastery": 5, "master": 5, "authority": 5,
}

# Default confidence weight by how an assessment was captured (feeds HRS "Trust in the Reading").
SOURCE_CONFIDENCE = {"self": 0.5, "manager": 0.8, "validated": 0.95}


def word_to_level(word) -> int:
    """Map a proficiency word ('Advanced') to the 1–5 scale; unknown → 3 (middle)."""
    return PROFICIENCY_WORD_TO_LEVEL.get(str(word).strip().lower(), 3)


def parse_skill_proficiency(text):
    """'Strategic vision:Expert; Board relations:Advanced' -> [('Strategic vision', 5), ...].

    Splits on ';', takes the level after the LAST ':' so skill names containing a
    colon survive. Blank / malformed pairs are skipped.
    """
    out = []
    for pair in str(text or "").split(";"):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        name, _, lvl = pair.rpartition(":")
        name = name.strip()
        if name:
            out.append((name, word_to_level(lvl)))
    return out

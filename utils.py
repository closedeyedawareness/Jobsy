def normalize_title(t: str) -> str:
    import re
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', t.lower())).strip()

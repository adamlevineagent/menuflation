"""normalize.py — menu item name normalization for matching."""
import re

# Common variants -> canonical token
_SYNONYMS = {
    "fries": "french fries",
    "fry": "french fries",
    "frenchfries": "french fries",
    "cheeseburger": "cheese burger",
    "cheeseburgers": "cheese burger",
    "cheese burger": "cheese burger",
    "hamburger": "hamburger",
    "burger": "hamburger",
    "coke": "coca cola",
    "cokes": "coca cola",
    "coca-cola": "coca cola",
    "diet coke": "diet coke",
}
_STRIP = re.compile(r"[^a-z0-9 ]+")


def normalize_name(name):
    """Lowercase, strip punctuation, collapse whitespace, map synonyms.

    Portion/size words are deliberately KEPT — they distinguish items
    (Double Cheeseburger != Cheeseburger); matching decides via
    portion-aware scoring instead.
    """
    if not name:
        return ""
    s = name.lower()
    s = _STRIP.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = " ".join(t for t in s.split(" ") if t)
    return _SYNONYMS.get(s, s)


def normalize_price(p):
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None
    if p <= 0 or p > 10000:  # sanity bounds
        return None
    return round(p, 2)

"""match.py — canonical item matching via portion-aware token-set similarity."""
from rapidfuzz import fuzz

from menuflation.normalize import normalize_name

DEFAULT_THRESHOLD = 88.0

# Words that make two item names DISTINCT items (portion/serving constructs).
# "Double Cheeseburger" is not "Cheeseburger"; "cheese burger" and
# "cheeseburger" are the same thing.
PORTION_WORDS = {
    "small", "medium", "large", "regular", "mini", "junior", "kids", "kid",
    "single", "double", "triple", "quarter", "half",
    "order", "basket", "plate", "side", "combo", "meal", "entree", "a la carte",
}


def _portion_only_diff(a, b):
    """True if the names differ only by portion/size words."""
    sa, sb = set(a.split()), set(b.split())
    if len(sa) == len(sb):
        return False
    diff = (sa - sb) | (sb - sa)
    return bool(diff) and diff.issubset(PORTION_WORDS)


def similarity(a, b):
    if _portion_only_diff(a, b):
        return 0.0
    return fuzz.token_set_ratio(a, b)


def canonicalize(names, threshold=DEFAULT_THRESHOLD):
    """Map raw item names to canonical names.

    Greedy clustering: each normalized name joins the first existing canonical
    whose portion-aware similarity clears the threshold, else starts a new one.
    Returns dict raw_name -> canonical_name.
    """
    reps = []  # (canonical_name, norm_name)
    mapping = {}
    for raw in names:
        n = normalize_name(raw)
        if not n:
            continue
        best, best_score = None, 0.0
        for canon, rep in reps:
            sc = similarity(n, rep)
            if sc > best_score:
                best, best_score = canon, sc
        if best is not None and best_score >= threshold:
            mapping[raw] = best
        else:
            reps.append((n, n))
            mapping[raw] = n
    return mapping


def canonicalize_place(conn, place_id, threshold=DEFAULT_THRESHOLD):
    """Match all raw items for one place into canonicals; write canonical_id."""
    rows = conn.execute(
        "SELECT id, item_raw FROM menu_lines WHERE place_id=?",
        (place_id,)).fetchall()
    if not rows:
        return 0
    mapping = canonicalize([r[1] for r in rows], threshold)
    canon_ids = {}
    for raw, canon in mapping.items():
        conn.execute("INSERT OR IGNORE INTO canonical_items(name) VALUES(?)",
                     (canon,))
        cid = conn.execute("SELECT id FROM canonical_items WHERE name=?",
                           (canon,)).fetchone()[0]
        canon_ids[raw] = cid
    for lid, raw in rows:
        cid = canon_ids.get(raw)
        if cid:
            conn.execute("UPDATE menu_lines SET canonical_id=? WHERE id=?",
                         (cid, lid))
    conn.commit()
    return len(set(canon_ids.values()))

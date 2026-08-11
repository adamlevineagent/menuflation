"""match.py — canonical item matching via portion-aware token-set similarity."""
import re

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

# Leading quantity + the rest, e.g. "5 Original Cheeseburgers".
_QTY = re.compile(r"^(\d+)[x×]?\s+(.*)$")
_SINGULAR = re.compile(r"s$")


def _tokens_singular(s):
    return {_SINGULAR.sub("", t) for t in s.split()}


def _quantity_bundle(a, b):
    """True if one name is a quantity bundle of the other ("5 Original
    Cheeseburgers" vs "Original Cheeseburger").  A pack SKU carries a bundle
    price, never a same-store price observation for the single item — merging
    them silently turns a $19.39 5-pack into a cheeseburger price.  Bias is
    toward distinctness (like PORTION_WORDS); a false split is safer than a
    false merge in a price series."""
    for x, y in ((a, b), (b, a)):
        m = _QTY.match(x)
        if m and _tokens_singular(m.group(2)) == _tokens_singular(y):
            return True
    return False


def _portion_only_diff(a, b):
    """True if the names differ only by portion/size words."""
    sa, sb = set(a.split()), set(b.split())
    if len(sa) == len(sb):
        return False
    diff = (sa - sb) | (sb - sa)
    return bool(diff) and diff.issubset(PORTION_WORDS)


def _strict_subset_ratio(a, b):
    """If one token set is a strict subset of the other, return
    len(shorter)/len(longer); otherwise None.  token_set_ratio gives 100
    for any subset relationship (e.g. "burrata" ⊂ "gioia burrata"), which
    merges a short fragment name into a longer, different dish — a false
    canonical that corrupts the price series."""
    sa, sb = set(a.split()), set(b.split())
    if sa < sb:
        return len(sa) / len(sb)
    if sb < sa:
        return len(sb) / len(sa)
    return None


def similarity(a, b):
    if _portion_only_diff(a, b) or _quantity_bundle(a, b):
        return 0.0
    score = fuzz.token_set_ratio(a, b)
    ratio = _strict_subset_ratio(a, b)
    if ratio is not None and ratio < 0.67:
        # A short fragment that happens to be a token-subset of a much
        # longer dish name is a different item.  Scale the score so a
        # 1:3 subset (burrata / gioia burrata) scores 33, not 100.
        score *= ratio
    return score


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

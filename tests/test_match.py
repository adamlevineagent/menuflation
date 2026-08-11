"""test_match.py — durable pytest coverage for canonical item matching.

The token_set_ratio subset bug: fuzz.token_set_ratio returns 100 whenever
one name's tokens are a strict subset of the other's, so a short fragment
("burrata") merges with a longer, different dish ("gioia burrata") —
corrupting the price series with extreme ratios.  The subset-scaling fix
scales the score by len(shorter)/len(longer) for strict subsets below the
0.67 ratio, keeping them as distinct canonicals.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from menuflation.match import similarity, canonicalize


class TestSubsetScaling:
    def test_short_subset_is_distinct(self):
        """1-token fragment of a 3-token dish must score below threshold."""
        assert similarity("burrata", "gioia burrata") < 88
        assert similarity("farmstead", "farmstead deviled eggs") < 88
        assert similarity("crispy potatoes", "grass fed cheeseburger with crispy potatoes") < 88
        assert similarity("kale salad", "salad of lacinato kale") < 88

    def test_exact_match_still_100(self):
        """Identical names must still score 100."""
        assert similarity("kale salad", "kale salad") == 100
        assert similarity("smoked chicken club", "smoked chicken club") == 100

    def test_near_match_above_threshold(self):
        """Case-only differences (already normalized) should still match."""
        assert similarity("smoked chicken club", "smoked chicken club") >= 88

    def test_canonicalize_splits_false_merges(self):
        """canonicalize() must NOT merge a fragment with a longer dish."""
        names = ["Burrata", "Gioia Burrata", "Farmstead", "Farmstead Deviled Eggs"]
        mapping = canonicalize(names)
        canon = set(mapping.values())
        # All four should be distinct canonicals
        assert len(canon) == 4, f"Expected 4 canonicals, got {len(canon)}: {mapping}"

    def test_canonicalize_keeps_true_pairs(self):
        """Same item with cosmetic case differences must still collapse."""
        names = ["Smoked Chicken Club", "smoked chicken club", "SMOKED CHICKEN CLUB"]
        mapping = canonicalize(names)
        assert len(set(mapping.values())) == 1, f"Expected 1 canonical, got {mapping}"

    def test_quantity_bundle_is_distinct(self):
        """A pack SKU ("5 Original Cheeseburgers") must NOT merge into the
        single item's canonical — the bundle price would poison the series
        (Burgerville $19.39 5-pack read as a cheeseburger price, Aug 2026)."""
        # Same name after the quantity -> guard fires (bundle != single).
        assert similarity("5 Original Cheeseburgers", "Original Cheeseburger") == 0.0
        assert similarity("Original Cheeseburger", "5 Original Cheeseburgers") == 0.0
        # "Original" token differs too, so it clears the guard but must stay
        # below threshold either way.
        assert similarity("5 Original Cheeseburgers", "Cheeseburger") < 88
        names = ["Original Cheeseburger", "5 Original Cheeseburgers",
                 "5 Original Cheeseburgers + 2 Large Fries",
                 "Bacon Cheeseburger", "Double Cheeseburger"]
        mapping = canonicalize(names)
        assert mapping["Original Cheeseburger"] == "original cheeseburger"
        assert mapping["5 Original Cheeseburgers"] != "original cheeseburger"
        assert mapping["Bacon Cheeseburger"] == "bacon cheeseburger"

    def test_quantity_bundle_keeps_true_sizes(self):
        """Real size/measurement constructs must be untouched by the bundle
        guard (normalized measurement tokens are stripped upstream)."""
        assert similarity("12 oz ribeye", "ribeye") > 0  # not a quantity bundle
        assert similarity("double cheeseburger", "cheeseburger") == 0.0  # portion guard intact

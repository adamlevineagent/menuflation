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

"""test_web_extraction.py — durable verification for web-source extraction
payloads (Olo/Toast order-platform DOM captures).

The Burgerville capture (2026-08-10) is the reference artifact: a web
extraction must carry the same-store place_id, an honest date, and items
that canonicalize WITHOUT polluting the single-item series (the "5 Original
Cheeseburgers" bundle merges into "original cheeseburger" without the
quantity-bundle guard in menuflation.match).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from menuflation.match import canonicalize

_BV_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "extractions", "web",
    "ChIJL3qwyg-hlVQRK3LBcpuq72k", "order_burgerville_com_menu_2026-08-10.json",
)


def test_burgerville_web_extraction_schema():
    with open(_BV_FILE, encoding="utf-8") as fh:
        d = json.load(fh)
    assert d["place_id"] == "ChIJL3qwyg-hlVQRK3LBcpuq72k"          # anchor store
    assert d["date_source"] == "web"
    assert d["observed_on"] == "2026-08-10"
    assert d["result"]["is_menu"] is True
    items = d["result"]["items"]
    assert len(items) >= 38
    prices = {i["name"]: i["price"] for i in items}
    # Live-board anchors for the 16-year same-store series.
    assert prices["Original Cheeseburger"] == 4.49
    assert prices["Double Cheeseburger"] == 6.69
    assert prices["Bacon Cheeseburger"] == 9.69
    assert all(isinstance(p, (int, float)) and p > 0 for p in prices.values())


def test_burgerville_bundle_stays_out_of_single_item_canonical():
    """The 5-pack bundle SKU must get its own canonical, not merge into
    original cheeseburger (that pollution put $19.39 in a $4.49 series)."""
    with open(_BV_FILE, encoding="utf-8") as fh:
        d = json.load(fh)
    names = [i["name"] for i in d["result"]["items"]]
    mapping = canonicalize(names)
    assert mapping["Original Cheeseburger"] == "original cheeseburger"
    assert mapping["5 Original Cheeseburgers"] != "original cheeseburger"
    assert mapping["5 Original Cheeseburgers + 2 Large Fries"] != "original cheeseburger"

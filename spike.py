"""Spike: prove the qwen seam. Usage: python spike.py <image.jpg> [more images...]"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from menuflation.extract.qwen_vision import check_key, extract_menu_photo


def main(paths):
    key = check_key()
    print("key:", json.dumps(key, indent=2))
    for p in paths:
        print(f"\n=== {p} ===")
        res = extract_menu_photo(p)
        print(f"cost ${res['cost_usd']:.6f} ({res['tokens_in']} in / {res['tokens_out']} out)")
        print(json.dumps(res["data"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])

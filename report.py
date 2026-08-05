"""report.py — human-readable views over the current database.

Usage: python report.py [--retry-fails]
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    retry = "--retry-fails" in sys.argv[1:]
    if retry:
        _retry_failed()
    conn = sqlite3.connect(os.path.join("data", "menuflation.db"))
    _print_menus(conn)
    _print_chain_items(conn)
    _print_top_items(conn)
    _print_currency_check(conn)


def _retry_failed():
    import extract
    from menuflation.extract.qwen_vision import extract_menu_photo

    idx = json.load(open(os.path.join("data", "extractions", "index.json"),
                         encoding="utf-8"))
    done = set(idx)
    fails = [t for t in extract.build_tasks() if t[2] not in done]
    print(f"== {len(fails)} unextracted tasks ==")
    for slug, pid, pname, src in fails[:5]:
        try:
            res = extract_menu_photo(src)
            print(f"  retry OK  {slug}: is_menu={res['data'].get('is_menu')} "
                  f"${res['cost_usd']}")
        except Exception as e:  # noqa: BLE001
            print(f"  retry FAIL {slug}: {str(e)[:100]}")


def _print_menus(conn):
    print("\n== menus found per place ==")
    rows = conn.execute(
        "SELECT pl.name, COUNT(DISTINCT m.photo_ref), COUNT(m.id) "
        "FROM menu_lines m JOIN places pl ON pl.id=m.place_id "
        "GROUP BY pl.name ORDER BY COUNT(m.id) DESC").fetchall()
    for name, nphotos, nlines in rows:
        print(f"  {name[:44]:<46} {nphotos} menu-photos, {nlines} lines")


def _print_chain_items(conn):
    print("\n== burger-family items (matching sanity) ==")
    rows = conn.execute(
        "SELECT ci.name, pl.name, m.price, m.notes "
        "FROM menu_lines m JOIN canonical_items ci ON ci.id=m.canonical_id "
        "JOIN places pl ON pl.id=m.place_id "
        "WHERE ci.name LIKE '%burger%' OR ci.name LIKE '%fries%' "
        "ORDER BY ci.name, pl.name").fetchall()
    for name, place, price, notes in rows[:30]:
        print(f"  {name[:30]:<32} {place[:24]:<26} ${price:<6} {str(notes or '')[:24]}")


def _print_top_items(conn):
    print("\n== most common canonical items ==")
    rows = conn.execute(
        "SELECT ci.name, COUNT(*) n, ROUND(AVG(m.price),2) avg_px "
        "FROM menu_lines m JOIN canonical_items ci ON ci.id=m.canonical_id "
        "GROUP BY ci.name ORDER BY n DESC LIMIT 12").fetchall()
    for name, n, avg in rows:
        print(f"  {name[:40]:<42} {n:>3} obs, avg ${avg}")


def _print_currency_check(conn):
    print("\n== currency mix ==")
    for row in conn.execute(
            "SELECT currency_iso, COUNT(*) FROM menu_lines GROUP BY currency_iso"):
        print(f"  {row[0] or 'null'}: {row[1]}")


if __name__ == "__main__":
    main()

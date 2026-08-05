"""Verify Barney's dedup: one place, combined lines from both sources."""
import sqlite3
db = sqlite3.connect('data/menuflation.db')
db.row_factory = sqlite3.Row

# 1. Only one Barney's place
barneys = [r['id'] for r in db.execute("SELECT id FROM places WHERE name LIKE '%Barney%'")]
assert len(barneys) == 1, f"Expected 1 Barney's, got {len(barneys)}: {barneys}"
print(f"PASS: 1 Barney's place ({barneys[0]})")

# 2. Combined lines include both date sources
lines = db.execute("SELECT date_source, COUNT(*) c FROM menu_lines WHERE place_id=? GROUP BY date_source", barneys).fetchall()
sources = {r['date_source']: r['c'] for r in lines}
print(f"  date_sources: {sources}")
assert 'exif' in sources, "Missing exif lines (curly place not merged)"
assert 'dom' in sources, "Missing dom lines (straight place not merged)"
print(f"PASS: merged exif ({sources.get('exif',0)}) + dom ({sources.get('dom',0)}) lines")

# 3. Date range spans both
mn, mx = db.execute("SELECT MIN(observed_on), MAX(observed_on) FROM menu_lines WHERE place_id=?", barneys).fetchone()
print(f"  date range: {mn} -> {mx}")
assert mn.startswith('2024'), f"Expected 2024 start (dom), got {mn}"
print(f"PASS: temporal span {mn} -> {mx}")

# 4. Total places is 56 (was 57, one removed)
nplaces = db.execute("SELECT COUNT(*) FROM places").fetchone()[0]
print(f"  places: {nplaces}")
assert nplaces == 56, f"Expected 56 places, got {nplaces}"
print("PASS: 56 places (was 57, curly Barney's removed)")

# 5. Total menu_lines unchanged (no data lost)
nlines = db.execute("SELECT COUNT(*) FROM menu_lines").fetchone()[0]
print(f"  total menu_lines: {nlines}")
assert nlines >= 357, f"Expected >=357 lines, got {nlines}"
print("PASS: no data lost")

print("\nVERIFY: PASS")

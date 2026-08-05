"""extract.py — run qwen vision extraction over every collected photo.

Resumable: results land in data/extractions/<slug>/<place_id>/<ref>.json and a
global data/extractions/index.json maps photo_name -> result file, so
cross-query duplicates (same photo collected under two slugs) are never billed
twice. Failures are NOT indexed, so a re-run retries them.

Usage:
    python extract.py [--workers N] [--limit N]
"""
import glob
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from menuflation.extract.qwen_vision import check_key, extract_menu_photo  # noqa: E402

OUT = os.path.join("data", "extractions")
INDEX = os.path.join(OUT, "index.json")
WORKERS = 6

_lock = threading.Lock()


def load_index():
    if os.path.exists(INDEX):
        return json.load(open(INDEX, encoding="utf-8"))
    return {}


def build_tasks():
    tasks = []
    for mf in sorted(glob.glob(os.path.join("data", "places", "*.json"))):
        slug = os.path.basename(mf)[:-5]
        m = json.load(open(mf, encoding="utf-8"))
        for p in m["places"]:
            for ph in p["photos"]:
                tasks.append((slug, p["id"], ph["name"],
                              os.path.join("data", "places", ph["file"])))
    return tasks


def _do(src, attempts=2):
    last = None
    for i in range(attempts):
        try:
            return extract_menu_photo(src), None
        except Exception as e:  # noqa: BLE001 — report, don't kill the run
            last = e
            time.sleep(2 + i * 3)
    return None, last


def worker(task, index):
    slug, pid, pname, src = task
    if pname in index:
        return ("skip", pname, 0.0)
    res, err = _do(src)
    if res is None:
        return ("fail", pname, 0.0, str(err)[:120])
    ref = pname.rsplit("/", 1)[-1][:40]
    dest = os.path.join(OUT, slug, pid, ref + ".json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    payload = {
        "photo": pname, "src": src,
        "result": res.get("data"),
        "cost_usd": res.get("cost_usd"),
        "tokens_in": res.get("tokens_in"), "tokens_out": res.get("tokens_out"),
        "model": res.get("model"),
    }
    json.dump(payload, open(dest, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    with _lock:
        index[pname] = dest
        json.dump(index, open(INDEX, "w", encoding="utf-8"), indent=1)
    return ("done", pname, res.get("cost_usd", 0.0))


def main():
    workers = WORKERS
    limit = None
    argv = sys.argv[1:]
    if "--workers" in argv:
        i = argv.index("--workers")
        workers = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if "--limit" in argv:
        i = argv.index("--limit")
        limit = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]

    index = load_index()
    tasks = build_tasks()
    todo = [t for t in tasks if t[2] not in index]
    if limit:
        todo = todo[:limit]
    print(f"tasks: {len(tasks)} total, {len(todo)} to extract, "
          f"{len(tasks) - len(todo)} cached", flush=True)
    stats = {"done": 0, "skip": 0, "fail": 0, "cost": 0.0}
    t0 = time.time()
    if todo:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(worker, t, index): t for t in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    r = fut.result()
                except Exception as e:  # noqa: BLE001
                    stats["fail"] += 1
                    print(f"[fatal] {e}", flush=True)
                    continue
                kind = r[0]
                stats[kind] = stats.get(kind, 0) + 1
                if kind == "done":
                    stats["cost"] += r[2]
                if i % 25 == 0 or i == len(todo):
                    rate = i / max(time.time() - t0, 0.01)
                    print(f"[{i}/{len(todo)}] done={stats['done']} skip={stats['skip']} "
                          f"fail={stats['fail']} cost=${stats['cost']:.4f} "
                          f"({rate:.1f} photos/s)", flush=True)
    print(f"FINISHED: {json.dumps(stats)}", flush=True)
    key = check_key()
    if key.get("ok"):
        print(f"KEY USAGE NOW: ${key['usage']:.4f} / ${key['limit']} limit", flush=True)


if __name__ == "__main__":
    main()

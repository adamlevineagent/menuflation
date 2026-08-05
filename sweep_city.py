"""sweep_city.py — one-command city chain batch (the scale worker).

For one city (or all in scale.json): generate the chain-grid query list,
collect photos (resumable), extract (resumable, deduped), ingest, regenerate
the dashboard, verify, commit, push. Idempotent: re-running skips done work.

Usage:
    python sweep_city.py <city>          # one city from scale.json
    python sweep_city.py all             # every city in scale.json (default)
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = [sys.executable, "-u"]
ENV = dict(os.environ)
ENV.pop("PYTHONPATH", None)


def run(script, *args):
    r = subprocess.run(PY + [os.path.join(ROOT, script)] + list(args),
                       cwd=ROOT, env=ENV)
    if r.returncode != 0:
        raise SystemExit(f"{script} failed ({r.returncode})")


def build_queries(city, scale):
    qs = []
    for chain in scale["chains"]:
        qs.append({"query": f"{chain} {city['query']}",
                   "slug": f"{chain.replace(' ', '-')}-{city['name']}",
                   "city": city["name"].title(), "state": city["state"]})
    return qs


def main():
    scale = json.load(open(os.path.join(ROOT, "scale.json"), encoding="utf-8"))
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    cities = ([c for c in scale["cities"] if c["name"] == target]
              if target != "all" else scale["cities"])
    if not cities:
        raise SystemExit(f"no city '{target}' in scale.json")
    for city in cities:
        print(f"== {city['name']} ==", flush=True)
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(build_queries(city, scale), f)
            tmp = f.name
        try:
            run("collect.py", tmp, "--photos-per-place", "15")
            run("extract.py")
            run("upgrade_menus.py")
            run("dashboard.py")
            run("scripts/verify_aggregate.py")
        finally:
            os.unlink(tmp)
        subprocess.run(["git", "add", "-A"], cwd=ROOT)
        subprocess.run(["git", "-c", "user.name=adaml",
                        "-c", "user.email=adamlevineagent@users.noreply.github.com",
                        "commit", "-q", "-m",
                        f"sweep: {city['name']} chain batch (scale loop)"], cwd=ROOT)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT)
        print(f"== {city['name']} done ==", flush=True)
    print("SWEEP COMPLETE", flush=True)


if __name__ == "__main__":
    main()

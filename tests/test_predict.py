"""predict.py: the operator's perfection test as a reusable CLI.

Regression properties pinned against the committed data/menuflation.db:
- anchor default output is stable (hero item 2010-05-15 $1.49 -> 2026-08-10 $4.49);
- --place runs the same engines against any store and prints that store id.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_predict(*args):
    # strip the leaked PYTHONPATH so repo imports resolve cleanly
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "predict.py"), *args],
        capture_output=True, text=True, cwd=ROOT, env=env, timeout=120)


def test_anchor_default_stable():
    out = run_predict()
    assert out.returncode == 0, out.stderr
    assert "PERFECTION TEST" in out.stdout
    # hero item series: earliest dated point -> the 2026-08-10 capture
    assert "2010-05-15 $1.49 -> 2026-08-10 $4.49" in out.stdout


def test_place_arg_runs_other_store():
    out = run_predict("--place", "ChIJUS-dzWUGhYARysICSZjj8JU")  # Gott's Napa
    assert out.returncode == 0, out.stderr
    assert "store: ChIJUS-dzWUGhYARysICSZjj8JU" in out.stdout
    assert "PERFECTION TEST" in out.stdout
    # Gott's hero item auto-derived series ends at its 2026-08-10 capture
    assert "2026-08-10 $15.99" in out.stdout


def test_sparse_store_single_precapture_point():
    # Five Guys Medford: ONE pre-capture obs (2023-11-27 exif) + 2026 web
    # capture. The >=2 pre-capture auto-derive bar found nothing and crashed
    # on HERO[0]; the >=1 fallback must run the test instead.
    out = run_predict("--place", "ChIJd5LW92p7z1QRvnbaQnf3cmU")
    assert out.returncode == 0, out.stderr
    assert "PERFECTION TEST" in out.stdout
    assert "store: ChIJd5LW92p7z1QRvnbaQnf3cmU" in out.stdout
    # at least one hero item carries its 2023 -> 2026 same-store series
    assert "2023-11-27 $" in out.stdout and "-> 2026-08-10 $" in out.stdout


def test_auto_detect_capture_date_uses_stores_latest_obs():
    # North Medford's web capture is dated 2026-08-11 (one day later than the
    # old hardcoded default 2026-08-10). With no --capture, auto-detect must
    # pick the store's max observed_on (2026-08-11) so exact-date `caps` match
    # and the 2025-06-04 board -> 2026-08-11 web pair becomes testable.
    out = run_predict("--place", "ChIJ3-95C2N7z1QRdqWZDZz3lX4")
    assert out.returncode == 0, out.stderr
    assert "[auto] capture date -> 2026-08-11" in out.stdout
    assert "PERFECTION TEST (2026-08-11)" in out.stdout
    assert "store: ChIJ3-95C2N7z1QRdqWZDZz3lX4" in out.stdout
    # a hero item shows the 2025 board -> 2026 web same-store series
    assert "2025-06-04 $" in out.stdout and "-> 2026-08-11 $" in out.stdout


"""Run both PoCs (A1 + B1) against the emulator and write a combined
results file. The emulator must already be running and set up (see
tenv_setup.py for the trezor-user-env path, nix_setup.py for the
build-from-source path).

Usage:
    python poc/run_all.py --out poc-results
    python poc/run_all.py --out poc-results --trezor-path udp:127.0.0.1:21324
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import save_json

OUT_DEFAULT = "poc-results"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=OUT_DEFAULT)
    parser.add_argument("--trezor-path", default=None)
    parser.add_argument("--skip", default="", help="comma list of pocs to skip, e.g. a1")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    skip = {s.strip().lower() for s in args.skip.split(",") if s.strip()}

    summary: dict = {"a1": None, "b1": None}
    for name in ("a1", "b1"):
        if name in skip:
            summary[name] = {"verdict": "SKIPPED"}
            continue
        try:
            mod = __import__(f"poc_{name}")
            summary[name] = mod.main(str(out_dir / f"{name}.json"), args.trezor_path)
        except Exception:
            summary[name] = {
                "verdict": "ERROR",
                "error": traceback.format_exc(),
            }
            print(f"{name.upper()} ERRORED", file=sys.stderr)
            traceback.print_exc()

    save_json(summary, out_dir / "summary.json")
    print("SUMMARY:", {k: (v or {}).get("verdict") for k, v in summary.items()})
    failed = [k for k, v in summary.items() if (v or {}).get("verdict") in ("ERROR", "INCONCLUSIVE")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

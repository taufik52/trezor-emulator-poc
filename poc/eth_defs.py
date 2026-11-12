# Vendored + trimmed from trezor-firmware `tests/definitions.py`
# (https://github.com/trezor/trezor-firmware, LGPL-3.0).
# Only the helpers needed to build dev-signed ERC-7730 display formats
# and token definitions for the emulator. The emulator accepts definitions
# signed with the *dev* keys (trezorlib.testing.common.PRIVATE_KEYS_DEV);
# production devices only accept Trezor-signed definitions.
"""Build dev-signed Ethereum definition payloads for the emulator."""

from __future__ import annotations

import io
import struct
import typing as t
from hashlib import sha256

from trezorlib import cosi, messages, protobuf
from trezorlib.testing.common import PRIVATE_KEYS_DEV


def make_eth_token(
    symbol: str = "FAKE",
    decimals: int = 18,
    address: bytes = b"",
    chain_id: int = 0,
    name: str = "Fake token",
) -> messages.EthereumTokenInfo:
    return messages.EthereumTokenInfo(
        symbol=symbol,
        decimals=decimals,
        address=address,
        chain_id=chain_id,
        name=name,
    )


def make_payload(
    magic: bytes = b"trzd",
    format_version: bytes = b"2",
    data_type: messages.DefinitionType = messages.DefinitionType.ETHEREUM_NETWORK,
    timestamp: int = 0xFFFF_FFFF,
    message: protobuf.MessageType | bytes = None,  # type: ignore[assignment]
) -> bytes:
    if isinstance(message, bytes):
        message_bytes = message
    else:
        writer = io.BytesIO()
        protobuf.dump_message(writer, message)
        message_bytes = writer.getvalue()

    # Payload bytes are packed by hand (struct) instead of
    # trezorlib.definitions.DefinitionPayload: PyPI trezor 0.20.2 dropped the
    # 1-byte format-version field (its FORMAT_MAGIC is b"trzd1"), but the
    # firmware under test (dc067f5, core/embed/rust/src/definitions/blob.rs
    # parse_and_verify) requires magic b"trzd" + 1-byte version (b"2" = V2)
    # + 1-byte type + u32-LE timestamp + u16-LE length + data.
    # Verified locally: these bytes are identical to the firmware-vendored
    # trezorlib DefinitionPayload.build() output.
    payload = (
        magic
        + format_version
        + bytes([int(data_type)])
        + struct.pack("<I", timestamp)
        + struct.pack("<H", len(message_bytes))
        + message_bytes
    )
    return payload


def sign_payload(
    payload: bytes,
    merkle_neighbors: list[bytes],
    threshold: int = 3,
) -> tuple[bytes, bytes]:
    digest = sha256(b"\x00" + payload).digest()
    merkle_proof = []
    for item in merkle_neighbors:
        left, right = min(digest, item), max(digest, item)
        digest = sha256(b"\x01" + left + right).digest()
        merkle_proof.append(digest)

    merkle_proof = len(merkle_proof).to_bytes(1, "little") + b"".join(merkle_proof)
    # No deterministic=True: PyPI trezor 0.20.2 sign_with_privkeys takes
    # only (digest, privkeys) — the deterministic kwarg exists only in the
    # firmware-vendored trezorlib. Random nonces are fine here; the
    # signature only has to verify against the dev keys on the device.
    signature = cosi.sign_with_privkeys(digest, PRIVATE_KEYS_DEV[:threshold])
    sigmask = 0
    for i in range(threshold):
        sigmask |= 1 << i
    sigmask_byte = sigmask.to_bytes(1, "little")
    return merkle_proof, sigmask_byte + signature


def encode_eth_token(
    token: messages.EthereumTokenInfo | None = None,
    symbol: str = "FakeTok",
    decimals: int = 18,
    address: t.AnyStr = b"",
    chain_id: int = 0,
    name: str = "Fake token",
) -> bytes:
    if token is None:
        if isinstance(address, str):
            if address.startswith("0x"):
                address = address[2:]
            address = bytes.fromhex(address)  # type: ignore[is not assignable to]
        token = make_eth_token(symbol, decimals, address, chain_id, name)  # type: ignore[cannot be assigned to]
    payload = make_payload(
        data_type=messages.DefinitionType.ETHEREUM_TOKEN, message=token
    )
    proof, signature = sign_payload(payload, [])
    return payload + proof + signature


def make_eth_display_format(
    chain_id: int = 0,
    address: t.AnyStr = b"",
    func_sig: bytes = b"",
    intent: str = "Fake intent",
    parameter_definitions: list[messages.EthereumABIValueInfo] | None = None,
    field_definitions: list[messages.EthereumERC7730FieldInfo] | None = None,
) -> messages.EthereumDisplayFormatInfo:
    if isinstance(address, str):
        if address.startswith("0x"):
            address = address[2:]
        address_bytes = bytes.fromhex(address)
    else:
        address_bytes = address
    return messages.EthereumDisplayFormatInfo(
        chain_id=chain_id,
        address=address_bytes,
        func_sig=func_sig,
        intent=intent,
        parameter_definitions=parameter_definitions or [],
        field_definitions=field_definitions or [],
    )


def encode_eth_display_format(
    display_format: messages.EthereumDisplayFormatInfo,
) -> bytes:
    payload = make_payload(
        data_type=messages.DefinitionType.ETHEREUM_DISPLAY_FORMAT,
        message=display_format,
    )
    proof, signature = sign_payload(payload, [])
    return payload + proof + signature

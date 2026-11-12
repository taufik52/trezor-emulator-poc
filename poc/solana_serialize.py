"""Pure-stdlib Solana v0 message serialization.

Same layout as trezor-firmware's
`tests/device_tests/solana/construct/transaction.py` Message struct
(version byte, header, static accounts, blockhash, instructions, LUTs).
No trezorlib dependency, so this module can be unit-tested anywhere.
"""

from __future__ import annotations

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + _B58_ALPHABET.index(ch)
    # Leading '1's are leading zero bytes.
    pad = 0
    for ch in s:
        if ch == "1":
            pad += 1
        else:
            break
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * pad + raw


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, rem = divmod(n, 58)
        out = _B58_ALPHABET[rem] + out
    pad = 0
    for byte in data:
        if byte == 0:
            pad += 1
        else:
            break
    return "1" * pad + (out or "")


def compact_u16(value: int) -> bytes:
    """Solana short-vec (compact-u16) encoding."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def serialize_v0(
    header: tuple[int, int, int],
    accounts: list[str],
    blockhash: str,
    instructions: list[dict],
    luts: list[dict],
) -> bytes:
    """Serialize a v0 (versioned) Solana message.

    instructions: [{"program_id": int, "accounts": [int], "data": bytes}]
    luts: [{"table": str, "writable": [int], "readonly": [int]}]
    """
    buf = bytearray()
    buf.append(0x80)  # version 0 (high bit set)
    buf += bytes(header)
    buf += compact_u16(len(accounts))
    for account in accounts:
        buf += b58decode(account)
    buf += b58decode(blockhash)
    buf += compact_u16(len(instructions))
    for ix in instructions:
        buf.append(ix["program_id"])
        buf += compact_u16(len(ix["accounts"]))
        buf += bytes(ix["accounts"])
        buf += compact_u16(len(ix["data"]))
        buf += ix["data"]
    buf += compact_u16(len(luts))
    for lut in luts:
        buf += b58decode(lut["table"])
        buf += compact_u16(len(lut["writable"]))
        buf += bytes(lut["writable"])
        buf += compact_u16(len(lut["readonly"]))
        buf += bytes(lut["readonly"])
    return bytes(buf)


def system_transfer_data(lamports: int) -> bytes:
    # System Program: instruction id 2 (u32 LE) + lamports (u64 LE).
    return (2).to_bytes(4, "little") + lamports.to_bytes(8, "little")

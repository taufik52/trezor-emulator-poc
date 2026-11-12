"""Shared plumbing for the A1/B1 PoCs: connect to the emulator, run a signing
call with trezorlib's own `default_input_flow` (confirm-all, layout aware),
and record every screen shown.

The emulator is driven exactly like trezor-firmware's device tests do:
a `TrezorTestContext` over the transport, `get_session()`, and
`test_ctx.ui.default_input_flow(on_page=...)`. This handles pagination and
hold-to-confirm per layout, so no screen-specific button logic is needed here.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from trezorlib import messages
from trezorlib.debuglink import TrezorTestContext
from trezorlib.debuglink import LayoutContent
from trezorlib.transport import enumerate_devices, get_transport

# Standard public test mnemonic used by trezor-firmware's own test suite.
# Test data only — never use for real funds.
TEST_MNEMONIC = "all all all all all all all all all all all all art"


def find_transport(path: str | None = None, timeout: float = 120):
    """Wait for a debuggable device and return its transport.

    `path` may be a TREZOR_PATH value (e.g. "udp:127.0.0.1:21324").
    Without it, enumerate all transports and take the first one found.
    """
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if path:
                return get_transport(path, prefix_search=True)
            devices = list(enumerate_devices())
            if devices:
                return devices[0]
        except Exception as exc:  # noqa: BLE001 - retry until deadline
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"no Trezor device found (last error: {last_error})")


def open_session(path: str | None = None, timeout: float = 120):
    """Return (test_ctx, session) for the emulator. Caller must enter the
    context manager (`with test_ctx:`) around the signing calls."""
    transport = find_transport(path, timeout=timeout)
    test_ctx = TrezorTestContext(transport)
    session = test_ctx.get_session()
    return test_ctx, session


class ScreenRecorder:
    """Collects every distinct screen text seen via the input-flow callback."""

    def __init__(self) -> None:
        self.pages: list[str] = []

    def on_page(self, layout: LayoutContent) -> None:
        try:
            text = layout.text_content()
        except Exception:
            text = ""
        if text and (not self.pages or self.pages[-1] != text):
            self.pages.append(text)

    def all_text(self) -> str:
        return "\n---PAGE---\n".join(self.pages)

    def contains(self, needle: str, case_insensitive: bool = False) -> bool:
        hay = self.all_text()
        if case_insensitive:
            return needle.lower() in hay.lower()
        return needle in hay


def run_signing(test_ctx: TrezorTestContext, session, sign_fn, timeout: float = 180):
    """Run `sign_fn(session)` with confirm-all input flow; return a dict with
    the signature (hex) or the error, plus every screen shown."""
    recorder = ScreenRecorder()
    outcome: dict = {"pages": recorder.pages}
    with test_ctx:
        test_ctx.set_input_flow(
            test_ctx.ui.default_input_flow(on_page=recorder.on_page)
        )
        try:
            result = sign_fn(session)
            outcome["signature"] = (
                result.hex() if isinstance(result, (bytes, bytearray)) else str(result)
            )
            outcome["signed"] = True
        except Exception as exc:  # noqa: BLE001 - recorded as the verdict
            outcome["signed"] = False
            outcome["error"] = f"{type(exc).__name__}: {exc}"
    return outcome


def fw_info(session) -> dict:
    f = session.features
    return {
        "model": str(getattr(session, "layout_type", "")),
        "fw_version": ".".join(str(x) for x in (f.major_version, f.minor_version, f.patch_version)),
        "fw_vendor": getattr(f, "fw_vendor", ""),
        "label": getattr(f, "label", ""),
    }


def save_json(data: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

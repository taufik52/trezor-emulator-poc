"""Minimal websocket client for the trezor-user-env controller (port 9001).

Protocol (see https://github.com/trezor/trezor-user-env/blob/master/docs/controller.md):
requests are JSON objects with a `type` key; responses echo the request `id`
and carry a boolean `success` key.
"""

from __future__ import annotations

import json
import time

import websocket

DEFAULT_URL = "ws://127.0.0.1:9001"


class TenvError(RuntimeError):
    pass


class TenvClient:
    def __init__(self, url: str = DEFAULT_URL, timeout: float = 30.0):
        self.url = url
        self.timeout = timeout
        self._ws: websocket.WebSocket | None = None
        self._next_id = 1

    def __enter__(self) -> "TenvClient":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def connect(self) -> None:
        self._ws = websocket.create_connection(self.url, timeout=self.timeout)
        # The controller sends a welcome message on connect; drain it.
        try:
            self._ws.settimeout(2)
            self._ws.recv()
        except Exception:
            pass
        finally:
            if self._ws is not None:
                self._ws.settimeout(self.timeout)

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def call(self, cmd_type: str, timeout: float | None = None, **kwargs) -> dict:
        if self._ws is None:
            raise TenvError("not connected")
        req_id = self._next_id
        self._next_id += 1
        payload = {"type": cmd_type, "id": req_id, **kwargs}
        self._ws.settimeout(timeout or self.timeout)
        self._ws.send(json.dumps(payload))
        deadline = time.time() + (timeout or self.timeout)
        while True:
            if time.time() > deadline:
                raise TenvError(f"timeout waiting for response to {cmd_type}")
            raw = self._ws.recv()
            try:
                resp = json.loads(raw)
            except Exception:
                continue
            if resp.get("id") != req_id:
                # Unsolicited / welcome traffic; keep waiting.
                continue
            if not resp.get("success", False):
                raise TenvError(f"{cmd_type} failed: {resp.get('error', resp)}")
            return resp

    # -- convenience wrappers -------------------------------------------------
    def ping(self) -> dict:
        return self.call("ping")

    def background_check(self) -> dict:
        return self.call("background-check")

    def bridge_start(self) -> dict:
        return self.call("bridge-start")

    def emulator_start(
        self, model: str = "T2T1", version: str | None = None, wipe: bool = True
    ) -> dict:
        kwargs: dict = {"model": model, "wipe": wipe}
        if version is not None:
            kwargs["version"] = version
        return self.call("emulator-start", timeout=300, **kwargs)

    def emulator_setup(
        self,
        mnemonic: str,
        pin: str = "",
        label: str = "poc",
        passphrase_protection: bool = False,
        needs_backup: bool = False,
    ) -> dict:
        return self.call(
            "emulator-setup",
            timeout=120,
            mnemonic=mnemonic,
            pin=pin,
            label=label,
            passphrase_protection=passphrase_protection,
            needs_backup=needs_backup,
        )

    def emulator_stop(self) -> dict:
        return self.call("emulator-stop")

    def get_debug_state(self) -> dict:
        """Returns the response dict; `layout_lines` holds the screen text."""
        resp = self.call("emulator-get-debug-state", timeout=15)
        return resp.get("response", {})

    def get_screenshot_b64(self) -> str:
        resp = self.call("emulator-get-screenshot", timeout=15)
        return str(resp.get("response", ""))

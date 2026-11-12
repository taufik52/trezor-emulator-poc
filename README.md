# trezor-emulator-poc

Proof-of-concept executions for two Trezor firmware (Core) findings, run
against the firmware **emulator** in GitHub Actions — no hardware, no
payment, no secrets.

| Finding | Summary |
| --- | --- |
| **TREZOR-A1** (Medium) | Any `ClearSigningFailed` in ERC-7730 clear signing is swallowed and the device silently falls back to blind signing — no warning that the clear-signed view was lost. (`core/src/apps/ethereum/sign_tx.py:183-190`) |
| **TREZOR-B1** (Medium) | A Solana v0 transfer whose recipient is an Address Lookup Table (ALT) reference is confirmed without ever showing the actual recipient address — only the table address + index. (`core/src/apps/solana/transaction/__init__.py:376-384`, `layout.py:50-58`) |

Audit target: trezor-firmware @ `dc067f5` (main, 2026-11-12).
Full audit reports: `trezor-audit/findings/TREZOR-A1-*.md` and
`TREZOR-B1-*.md` (private workspace, not this repo).

## How it works

1. The workflow starts the firmware emulator — primary path via the
   official [`trezor-user-env`](https://github.com/trezor/trezor-user-env)
   Docker image (`ghcr.io/trezor/trezor-user-env`, model T2T1, latest
   main build); fallback job builds the emulator from source with nix.
2. The public test mnemonic (`all all ... art`, trezor-firmware's own test
   vector — test data only) is loaded into the emulator.
3. `poc/run_all.py` runs both PoCs with `trezorlib` exactly like
   trezor-firmware's device tests do (`TrezorTestContext`,
   `default_input_flow` confirm-all, screen text recorded via `on_page`).

Each PoC has a **control** (proves the environment can show the correct
screen) and a **test** (the vulnerable shape):

- **A1 control:** valid ERC-7730 display format + valid calldata →
  clear-signed labels (`FAKE Amount`, …) must appear.
  **A1 test:** the same format with an extra tuple field (parsing fails
  with `OutOfBounds`, a `ClearSigningFailed`) and a dirty-address variant →
  labels must be absent, no "clear signing" warning anywhere, raw calldata
  hex shown, signature still produced.
- **B1 control:** v0 transfer with a static recipient → recipient address
  must appear on screen.
  **B1 test:** the same transfer with the recipient loaded from an ALT →
  the recipient address must never appear; only the table address + index
  are shown; signature still produced.

Verdicts per PoC: `CONFIRMED`, `NOT_REPRODUCED`, `INCONCLUSIVE`
(control failed — environment problem, not a finding verdict), or `ERROR`.

## Run it

Push to `main` or trigger **Actions → emulator-poc → Run workflow**.
Results (per-PoC JSON with every screen shown + a combined summary) are
uploaded as the `poc-results-tenv` artifact (or `poc-results-nix` if the
fallback ran).

## Local run (needs a running emulator)

```sh
pip install -r requirements.txt
# trezor-user-env path:
python poc/tenv_setup.py
python poc/run_all.py --out poc-results
# or build-from-source path (emulator already running headless):
TREZOR_PATH=udp:127.0.0.1:21324 python poc/nix_setup.py
python poc/run_all.py --out poc-results --trezor-path udp:127.0.0.1:21324
```

## Layout

- `poc/tenv.py` — websocket client for the trezor-user-env controller.
- `poc/common.py` — device connect + confirm-all signing driver.
- `poc/eth_defs.py` — dev-signed ERC-7730 definition builders (vendored
  from trezor-firmware `tests/definitions.py`, LGPL-3.0).
- `poc/solana_serialize.py` — pure-stdlib Solana v0 message serializer.
- `poc/poc_a1.py`, `poc/poc_b1.py` — the two PoCs.
- `poc/run_all.py` — orchestrator, writes `poc-results/summary.json`.

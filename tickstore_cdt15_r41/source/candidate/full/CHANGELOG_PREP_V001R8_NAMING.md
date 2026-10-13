# CHANGELOG — TICKSTORE V001R8 GATE B WINDOWS

Date: 2026-09-24

## Purpose
Canonical project rename: `PEGASUS TICKSTORE` -> `TICKSTORE`, requested by owner to avoid confusion with the Pegasus EA.

## Active-name changes
- package prefix: `TICKSTORE`;
- default destination: `D:\TICKSTORE`;
- default scratch: `D:\TICKSTORE_GATE_B_SCRATCH`;
- runner schema: `TICKSTORE_SERIAL_RUNNER_V001R8_GATE_B_WINDOWS`;
- journal/commit/manifest schemas bumped to TICKSTORE V003;
- preflight schema/file bumped to `TICKSTORE_WINDOWS_GATE_B_PREFLIGHT_V005` / `WINDOWS_GATE_B_PREFLIGHT_V005.py`;
- owner gate schema bumped to `TICKSTORE_PILOT_OWNER_GATE_V002`;
- active preflight/banner/fault-injection/full-gate labels use only `TICKSTORE`.

## Frozen historical compatibility
`pts2g_reference.py`, `OUT_P4A_R3_FULL_HISTORY_COMPAT.zip`, PTS2G001 format semantics and historical audit documents are preserved byte-for-byte where required. Historical references may therefore retain the legacy project name.

## Functional scope
No codec, PTS2G001 payload/index, source parser, row-group size, Windows hardlink/ancestor-pin, writer-lock, ENOSPC, atomic publication, safe-stop or FULL-history authorization logic is intentionally changed.

## Gate state
- prior R7 low pilot 20260731: execution PASS, preserved as historical evidence;
- R8 requires new PLAN/PREFLIGHT_LOW/owner gate and repeat low pilot because runner/spec/preflight hashes changed;
- PILOT_HIGH: NO; FULL: NO; AUTOCPU: NO; CSV deletion: NO.

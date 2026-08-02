# HWiNFO Reader

**Script:** [HWiNFO Reader (script)](../hwinfo.py)

## Purpose

Reads sensor values from HWiNFO's shared-memory section
(`Global\HWiNFO_SENS_SM2`) when the third-party HWiNFO tool happens to be
running: CPU temperature / power / EDC for the CPU window, committed virtual
memory and DRAM read/write bandwidth for the Memory window. HWiNFO not
running is the normal case, not an error — the mapping simply fails to open
and an empty `HWiNFOData` comes back, which the windows render as an absent
sensor row. Sensor indices are discovered by one full scan on the first
successful read and cached; every later read is a direct offset lookup, and
the whole result is cached for half a second so several windows ticking at
once cost one read.

## Connections

### Uses
- Windows shared-memory APIs (`ctypes` — `OpenFileMappingW`,
  `MapViewOfFile`) only; no other Vitals module

### Used by
- [Process Stats](process_stats.md) — `get_hwinfo_data()` calls
  `read_sensors()` once per tick
- [Monitor Data](monitor_data.md) — imports `HWiNFOData` as the type of
  `MonitorData.hwinfo`
- [Collector](collector.md) — imports `HWiNFOData` to build the empty
  fallback when no CPU monitor exists yet

## Classes

### `HWiNFOData` (dataclass)
The six optional readings: `cpu_tctl`, `cpu_power`, `cpu_edc`,
`virt_committed`, `dram_read`, `dram_write` — all `None` when not found or
HWiNFO is not running.

### `HWiNFOSharedMemory`
Owns the shared-memory handle lifecycle for one read. `get_sensors()` opens
the mapping, scans for sensor indices on first success (cached after that),
reads the six target values, and always releases the handle via `finally` —
a parsing exception can never leak it. Unexpected parsing failures are
logged to stderr once per process; a missing HWiNFO instance is not logged
at all.

## Functions

### `read_sensors() -> HWiNFOData`
Process-wide entry point. Lazily creates one `HWiNFOSharedMemory` reader so
the index scan and the half-second cache are only paid for once, however
many windows are ticking.

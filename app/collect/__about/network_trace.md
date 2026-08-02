# Network Trace

**Script:** [Network Trace (script)](../network_trace.py) ·
**Flow:** [diagram](../__flow/network_trace.md)

## Purpose

ETW (Event Tracing for Windows) capture of per-process network traffic.
`NetworkTracer` runs a real-time kernel session with
`EVENT_TRACE_FLAG_NETWORK_TCPIP` enabled; a background consumer thread
processes TCP/UDP send/receive events and increments per-PID byte counters,
which [Collector](collector.md) polls once per tick via
`snapshot_and_reset()`. Requires Administrator privileges — the kernel
logger cannot start otherwise. This module was `app/network_monitor.py`
before the god-file split. Every way capture can be unavailable — not just a
failed initial `start()` — surfaces as a structured `TraceFailure`, never a
bare string, so the Network window can pick the right remedy instead of
string-matching developer text. See [flow](../__flow/network_trace.md) for
the session lifecycle and its failure states.

## Connections

### Uses
- `app/persistence.py` — `get_data_dir()` resolves the opt-in debug log path
  (`../../__about/persistence.md`)

### Used by
- [Collector](collector.md) — `configure_network()` lazily imports
  `NetworkTracer`; `TraceFailure`, `CONSUMER_DIED`, `START_FAILED` are
  imported at module level so fallback failures can be built without the
  tracer itself
- [Monitor Data](monitor_data.md) — `TraceFailure`, the type of
  `NetworkMonitorData.error`
- [Windows (subfolder)](../../windows/___windows.md) — `base_window.py` and
  `status_banner.py` import `NEEDS_ADMIN` to pick the status-banner remedy;
  `network_window.py` imports `get_link_speed_mbps()` to resolve a `0`
  ("auto") max-speed setting
- [Dialogs (subfolder)](../../dialogs/___dialogs.md) — `setup_dialog.py`
  imports `get_link_speed_mbps()` for the default max-speed spinbox value

## Classes

### `TraceFailure` (frozen dataclass)
Why per-process network capture is unavailable, in words a user can act on:
`code` (one of the constants below), `reason` (plain language), `action`
(what the user can do), `detail` (raw API status, log-only). The `code`
lets the window pick the right remedy — relaunching elevated cannot fix
"another instance", retrying cannot fix "needs admin".

### `NetworkTracer`
Owns one ETW kernel trace session (`Vitals_NetTrace`) and its consumer
thread.

- `error` (property) — last `TraceFailure`, or `None` if running normally
- `start()` — starts the session and consumer thread; `True` on success,
  `False` (with `.error` set) otherwise
- `stop()` — stops the kernel session, closes the trace handle, joins the
  consumer thread, releases the owner mutex; idempotent
- `is_dead()` — `True` when the consumer thread ended on its own after a
  good `start()`
- `snapshot_and_reset()` — returns `{pid: (bytes_received, bytes_sent)}`
  accumulated since the last call, then clears the counters

## Constants
`NEEDS_ADMIN`, `OTHER_INSTANCE`, `START_FAILED`, `CONSUMER_DIED` — the
`TraceFailure.code` values.

## Functions

### `get_link_speed_mbps() -> int`
Link speed (Mbps) of the fastest "up" network interface via
`psutil.net_if_stats()`; falls back to 1000 Mbps if detection fails.

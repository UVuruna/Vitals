# Network Monitor (ETW Tracer)

**Script:** [network_monitor.py (script)](network_monitor.py)

---

## Purpose

Captures per-process network traffic (bytes sent/received) via a Windows
Event Tracing (ETW) real-time kernel session with
`EVENT_TRACE_FLAG_NETWORK_TCPIP` enabled. A background consumer thread
processes TCP/UDP send/receive events and increments per-PID byte counters;
[Monitor](monitor.md)'s `SharedDataCollector` polls `snapshot_and_reset()`
once per tick to turn the accumulated bytes into rates. Requires
Administrator privileges — the kernel logger cannot be started otherwise.

---

## Connections

### Uses

- [Persistence](persistence.md) — `get_data_dir()` resolves the opt-in debug log path

### Used by

- [Monitor](monitor.md) — `SharedDataCollector.configure_network()` lazily imports
  `NetworkTracer` and the module's `_log` logger on first network-mode enable
- [Main Window](main_window.md) — `NetworkWindow._resolve_max_bytes()` imports
  `get_link_speed_mbps()` to resolve a `0` ("auto") max-speed setting
- [Settings Dialog](settings_dialog.md) — `InitialSettingsDialog` and
  `NetworkSettingsDialog` import `get_link_speed_mbps()` for the default
  max-speed spinbox value

---

## Classes

### NetworkTracer

Owns one ETW kernel trace session (`Vitals_NetTrace`) and its consumer thread.

#### Attributes

- `error` (property): last error message, or `None` if running normally.

#### Methods

| Method | Description |
|--------|-------------|
| `start()` | Starts the ETW session and consumer thread. Returns `True` on success; `False` (with `.error` set) if not Administrator, another instance already owns the session, or `StartTraceW` fails. |
| `stop()` | Stops the kernel session, closes the trace handle, joins the consumer thread, and releases the owner mutex. Safe to call even if the consumer thread already died. |
| `snapshot_and_reset()` | Returns `{pid: (bytes_received, bytes_sent)}` accumulated since the last call, then clears the counters. |

---

## Functions

| Function | Description |
|----------|-------------|
| `get_link_speed_mbps()` | Returns the link speed (Mbps) of the fastest "up" network interface via `psutil.net_if_stats()`; falls back to 1000 Mbps if detection fails. Used to resolve `0` ("auto") in the max-download/upload speed settings. |

---

## Design Decisions

**Single-owner named mutex (`Global\Vitals_NetTrace_Owner`).** The ETW
session name (`Vitals_NetTrace`) is fixed system-wide, so a second Vitals
instance calling `StartTraceW` with the same name would silently steal or
kill the first instance's session. `start()` acquires this mutex first and
fails visibly (`self._error = "Another Vitals instance is already tracing
the network"`) instead of stealing it.

**`_session_started` is tracked separately from `_running`.** ETW kernel
sessions outlive the process that created them — if `ProcessTrace()` fails
or the consumer thread dies unexpectedly, `_running` goes `False` but the
kernel session is still live. `stop()` checks `_session_started` (not
`_running`) to guarantee `ControlTraceW(..., STOP)` always runs, so a crash
in the consumer can never leave a system-wide trace running until reboot.

**Debug logging is opt-in via `VITALS_DEBUG=1`.** The `etw_net` logger is a
`NullHandler` by default; only when the env var is set does it open
`get_data_dir()/logs/network_debug.log` in truncate mode. This keeps
production runs silent (no log spam, no risk of writing to a read-only
`Program Files` install) while still giving a way to diagnose ETW startup
failures during development.

**On tracer-start failure, the error surfaces in the UI instead of showing
zeros.** `SharedDataCollector` stores `tracer.error` and the Network window
displays it in place of the peak label (see `NetworkMonitorData.error` in
[Monitor](monitor.md)) — a silently-zero network window would look like a
bug rather than a permissions problem.

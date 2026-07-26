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
Every way capture can be unavailable — not just a failed initial `start()`
— is reported as a structured `TraceFailure`, never a bare string, so the
Network window can pick the right remedy instead of string-matching
developer text.

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

### TraceFailure (frozen dataclass)

Why per-process network capture is unavailable, in words a user can act on:
`code` (one of the constants below), `reason` (what went wrong, plain
language), `action` (what the user can do about it), `detail` (raw API
status, log-only, defaults to `""`). Replaces a bare error string — the
`code` lets the window pick the right remedy (relaunching elevated cannot
fix "another instance", retrying cannot fix "needs admin"), while `reason`
and `action` are the two lines the status banner shows.

### NetworkTracer

Owns one ETW kernel trace session (`Vitals_NetTrace`) and its consumer thread.

#### Attributes

- `error` (property): last `TraceFailure`, or `None` if running normally.

#### Methods

| Method | Description |
|--------|-------------|
| `start()` | Starts the ETW session and consumer thread. Returns `True` on success; `False` (with `.error` set) if not Administrator, another instance already owns the session, or `StartTraceW` fails. |
| `stop()` | Stops the kernel session, closes the trace handle, joins the consumer thread, and releases the owner mutex. Safe to call even if the consumer thread already died, and idempotent — a second call cannot double-close a handle. |
| `is_dead()` | `True` when the consumer thread ended on its own after a good `start()` — see Design Decisions. |
| `snapshot_and_reset()` | Returns `{pid: (bytes_received, bytes_sent)}` accumulated since the last call, then clears the counters. |

---

## Constants

`NEEDS_ADMIN`, `OTHER_INSTANCE`, `START_FAILED`, `CONSUMER_DIED` — the
`TraceFailure.code` values. Each names a distinct remedy: `NEEDS_ADMIN` →
relaunch elevated, `OTHER_INSTANCE` → exit the other Vitals instance,
`START_FAILED`/`CONSUMER_DIED` → retry.

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
fails visibly (`TraceFailure(OTHER_INSTANCE, ...)`) instead of stealing it.
A `NULL` handle from `CreateMutexW` is never treated as ownership — storing
it regardless (a real bug in an earlier version) made any non-183
`CreateMutexW` failure look like a successful acquire, and the code then
went on to stop the OTHER instance's live session.

**The admin check runs before the mutex check, not after.** The owner
mutex lives in the `Global\` namespace, so when an already-running ELEVATED
Vitals holds it, a non-elevated `CreateMutexW` fails with
`ERROR_ACCESS_DENIED` (5), NOT `ERROR_ALREADY_EXISTS` (183) — testing the
mutex first would miss that case entirely. The `NEEDS_ADMIN` message
therefore names both possible causes, since from inside `start()` they are
genuinely indistinguishable.

**`_session_started` is tracked separately from `_running`.** ETW kernel
sessions outlive the process that created them — if `ProcessTrace()` fails
or the consumer thread dies unexpectedly, `_running` goes `False` but the
kernel session is still live. `stop()` checks `_session_started` (not
`_running`) to guarantee `ControlTraceW(..., STOP)` always runs, so a crash
in the consumer can never leave a system-wide trace running until reboot.
`stop()` and `_release_owner_mutex()` are themselves idempotent — each
handle is cleared before it is closed, so a second call (e.g. once from the
collector thread and once from app shutdown) can never double-close it.

**`is_dead()` catches a consumer that fails AFTER `start()` already reported
success.** `start()` returns as soon as the consumer thread is spawned, so an
`OpenTraceW` failure, a non-zero `ProcessTrace`, an exception inside
`_consume()`, or the session being stopped externally all happen afterward.
Without a liveness check the tracer then returns empty snapshots forever and
every rate reads as a legitimate, permanent zero — indistinguishable from
"no network traffic". `is_dead()` is `_session_started and not _running and
not _stopping`: judged by liveness AND intent, because a clean `stop()` also
ends the consumer thread and must not be mistaken for a failure. The new
`_stopping` flag (set first thing in `stop()`) is what tells them apart; it
is also what `_consume()` checks before treating a clean `ProcessTrace`
return as `CONSUMER_DIED` — a return of 0 while nobody asked for a stop
means the kernel session was stopped from outside the process.

**Debug logging is opt-in via `VITALS_DEBUG=1`, but never fully silent.**
The `etw_net` logger defaults to a WARNING-level `StreamHandler(sys.stderr)`
— a refusal to start always leaves SOME record without the user first
needing to know an env var exists (root Rule #1). Only when the env var is
set does it switch to full DEBUG level and open
`get_data_dir()/logs/network_debug.log` in truncate mode, for diagnosing
ETW startup failures during development.

**On tracer failure — at start OR later — the error surfaces in the UI
instead of showing zeros.** `SharedDataCollector` stores the `TraceFailure`
and the Network window's status banner displays its `reason`/`action` (see
`NetworkMonitorData.error` in [Monitor](monitor.md)). A tracer that dies
after a successful start is retired via `is_dead()` on the next collector
tick, so a mid-session failure takes the same visible path as one that
never started — a silently-zero network window would look like a bug
rather than a permissions or session problem.

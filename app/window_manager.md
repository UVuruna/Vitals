# Window Manager

**Script:** [Window Manager (script)](window_manager.py)

---

## Purpose

Owns the three monitor windows as one group.

Which monitors existed used to be decided once, in `main.py`, from the setup
screen's checkboxes — so switching a monitor on later meant restarting the
app. This module makes it a runtime decision: it creates each window the
first time it is actually needed, shows and hides them, pushes one set of
settings into all of them, and keeps the CPU/Memory refresh-rate peering
wired.

That is what lets the tray's **Settings** action reopen the setup screen and
configure all three monitors in one place (owner 2026-07-24).

A window is never destroyed once created — hiding is enough, and its monitor
keeps running so peaks and history stay continuous.

---

## Connections

### Uses

- [Main Window](main_window.md) — `CPUWindow`, `MemoryWindow`, `NetworkWindow`, and each window's `apply_shared_settings()`
- [Monitor](monitor.md) — the shared `SharedDataCollector` passed to every window
- [Settings Dialog](settings_dialog.md) — `InitialSettings`, the one settings object all three modes read themselves out of

### Used by

- `main.py` — creates the manager and applies the startup settings
- [Tray Controller](tray.md) — toggles windows, opens Settings, and drives the exit sequence

---

## Constants

`MODES` — the display order and the `InitialSettings` flag that enables each
mode: `("cpu", "cpu_enabled")`, `("memory", "memory_enabled")`,
`("network", "network_enabled")`. The tray builds its menu from this, so a
fourth monitor would need no tray changes.

---

## Classes

### WindowManager

#### Methods

| Method | Description |
|--------|-------------|
| `existing()` | Every window created so far, in display order. |
| `window(key)` | One mode's window, or `None` if never needed. |
| `is_visible(key)` | Whether a mode's window exists and is on screen. |
| `show(key)` | Show a mode's window, **creating it on first use**. |
| `hide(key)` / `set_visible(key, visible)` | Hide, or show/hide by flag. |
| `hide_all()` / `show_all()` / `any_visible()` | Group operations for the tray's Minimize and double-click toggle. |
| `apply_settings(settings)` | Adopt one `InitialSettings` for every monitor and match window visibility to its mode flags. |
| `prepare_exit()` | Save every visible window's layout, then hide them all at once. |

### Applying shared settings

```
FUNCTION apply_settings(settings):
    remember settings as the current shared values
    FOR EACH (mode, enabled_flag) IN MODES:
        IF settings says this mode is enabled:
            IF its window does not exist yet → create and show it (it is
                                               built from these settings)
            ELSE                             → push the settings into it, then show
        ELSE:
            hide its window (if it exists)
```

Each window turns the shared object into its own per-mode settings dataclass
through `_settings_from_initial()` — the same hook its constructor uses, so
there is one definition of "what CPU reads out of the setup screen" rather
than two (root Rule #5).

---

## Design Decisions

**Lazy creation, never destruction.** Building a `NetworkWindow` starts the
ETW kernel trace, so creating all three up front would pay for a monitor the
user did not ask for. Creating on first enable avoids that; keeping the
window afterwards keeps its peak/history record continuous, which destroying
and rebuilding would throw away.

**Peering lives here.** `main.py` used to wire `cpu._peer_window` by hand
after constructing both windows. Now `_link_peers()` runs whenever a window
is created, so the pairing is correct no matter which order the monitors get
switched on in.

**`main.py` shrank to wiring.** Entry-point code now creates the collector,
the manager and the tray, and nothing else knows how a window is built.

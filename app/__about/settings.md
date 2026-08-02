# Settings

**Script:** [Settings (script)](../settings.py)

## Purpose

The user's settings, as one shared shape split into four dataclasses.
`InitialSettings` is what the setup screen produces — every monitor's
configuration in one object. Each window then keeps a per-mode slice of it
(`CPUSettings`, `MemorySettings`, `NetworkSettings`) so its own settings
dialog can change one monitor without touching the others. These live in
their own module, not beside a dialog, because three different layers read
them: the dialogs that edit them, the windows that apply them, and the
window manager that pushes one `InitialSettings` into all three monitors.

This module was created by the god-file split: it did not exist before, and
carries no legacy documentation.

## Connections

### Uses
- [Persistence](persistence.md) — `load_last_setup()` / `save_last_setup()` for `save_initial_settings()`
- [Styles](styles.md) — `Defaults`, the field default for every setting
- [Collect (subfolder)](../collect/___collect.md) — `get_commit_limit_bytes()`, imported lazily inside `InitialSettings.commit_limit_bytes` to avoid a top-level dependency on the collector package
- `psutil` — `InitialSettings.cpu_threads` / `.ram_gb` auto-detect from the live machine

### Used by
- [Window Manager](window_manager.md) — `InitialSettings`, the one settings object all three monitor modes read themselves out of
- [Windows (subfolder)](../windows/___windows.md) — each window's constructor and `apply_shared_settings()` read `InitialSettings` and store their own per-mode dataclass
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — the setup screen edits and returns `InitialSettings`; the three per-mode dialogs edit `CPUSettings` / `MemorySettings` / `NetworkSettings`
- `app/__init__.py` — re-exports all four dataclasses as the package's public settings API

## Classes

### InitialSettings
Settings from the setup screen (the launcher). Fields: `cpu_enabled`,
`memory_enabled`, `network_enabled`, `current_rows`, `history_rows`,
`refresh_rate_ms`, `retention_minutes`, `memory_unit`, `network_unit`,
`network_sort_mode`, `network_max_download_mbps`, `network_max_upload_mbps`,
`font_size`. Computed properties: `cpu_threads` / `ram_gb` (auto-detected via
`psutil`), `commit_limit_bytes` (via `collect.system_query`).

### CPUSettings / MemorySettings / NetworkSettings
Per-mode slices of the same shape — `current_rows`, `history_rows`,
`refresh_rate_ms`, `retention_minutes`, `font_size`, plus mode-specific
fields (`memory_unit` for Memory; `network_unit`, `sort_mode`,
`max_download_mbps`, `max_upload_mbps` for Network).

## Functions

| Function | Description |
|----------|--------------|
| `save_initial_settings(settings)` | Persists the setup screen's fields into `last_setup.json`. UPDATES the existing entry rather than replacing it — the same file also holds window layouts, themes, color thresholds and hue params. |

## Design Decisions

- **One shared shape, sliced per mode.** `InitialSettings` is the single
  source the setup screen produces; each window's own dataclass is a
  narrower read of the same fields, so a window's settings dialog can never
  drift from what the setup screen understands a monitor to be.
- **Auto-detected fields are properties, not stored values.** `cpu_threads`
  and `ram_gb` read the live machine on every access rather than being
  cached at construction, so they can never go stale across a long-running
  session.
- **`commit_limit_bytes` imports `collect.system_query` lazily**, inside the
  property, so `settings.py` (read by three layers) does not force a
  top-level dependency on the collection package for callers that never
  touch that one field.

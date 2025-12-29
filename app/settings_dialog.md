# Settings Dialog

**Script:** [settings_dialog.py (script)](settings_dialog.py)

---

## Purpose

Configuration dialog for Process Monitor settings. Allows user to select monitoring mode (CPU/Memory) and configure display options like refresh rate, number of rows, and memory units.

---

## Connections

### Uses

- [ProcessMonitor](monitor.md) - For MonitorMode enum
- [Styles](styles.md) - Colors, fonts, defaults

### Used by

- [MainWindow](main_window.md) - Opens dialog on startup and from menu

---

## Classes

### MonitorSettings

Dataclass containing all application settings.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | MonitorMode | CPU | CPU or MEMORY |
| `current_rows` | int | 7 | Processes to show |
| `history_rows` | int | 4 | History records |
| `refresh_rate_ms` | int | 2000 | Update interval |
| `retention_minutes` | int | 120 | History retention |
| `memory_unit` | str | "MB" | KB, MB, or GB |
| `cpu_threads` | int | auto | CPU thread count |
| `ram_gb` | int | auto | RAM in GB |

---

### SettingsDialog

Qt dialog for configuring settings.

#### Constructor

```python
SettingsDialog(
    parent: Optional[QWidget] = None,
    settings: Optional[MonitorSettings] = None,
)
```

#### Methods

- `get_settings()` -> MonitorSettings: Get current UI values

---

## UI Layout

```
┌───────────────────────────────────────┐
│         Process Monitor - Settings     │
├───────────────────────────────────────┤
│  Monitor Mode                          │
│  (●) CPU Usage  ( ) Memory Usage       │
├───────────────────────────────────────┤
│  Display Settings                      │
│  Current processes:    [  7  ▼]        │
│  History records:      [  4  ▼]        │
│  Refresh rate:     ═══════○═══  2000ms │
│  History retention: ═══○═══════  120min│
├───────────────────────────────────────┤
│  System Settings                       │
│  Memory unit:     [ MB ▼]              │
│  CPU threads:     [ 16 ▼]              │
│  RAM (GB):        [ 32 ▼]              │
├───────────────────────────────────────┤
│                    [Start Monitoring]  │
└───────────────────────────────────────┘
```

---

## Auto-Detection

On initialization, the dialog auto-detects:
- CPU thread count via `psutil.cpu_count()`
- RAM amount via `psutil.virtual_memory().total`

These values are pre-selected but can be overridden.

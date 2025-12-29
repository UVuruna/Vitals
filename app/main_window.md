# Main Window

**Script:** [main_window.py (script)](main_window.py)

---

## Purpose

The main application window that displays real-time process monitoring data. Contains header with statistics, current processes table, and historical peak usage table.

---

## Connections

### Uses

- [ProcessMonitor](monitor.md) - Data collection from psutil
- [SettingsDialog](settings_dialog.md) - Configuration UI
- [Styles](styles.md) - Colors, fonts, dimensions

### Used by

- `main.py` - Application entry point

---

## Classes

### HeaderWidget

Displays current total usage and peak statistics.

#### Methods

- `set_mode(mode)`: Update header style for CPU/Memory mode
- `update_stats(current, peak)`: Update displayed values

---

### ProcessTable

Table widget for displaying current process list.

#### Constructor

```python
ProcessTable(
    rows: int,
    show_cores: bool = True,
    header_color: str = Colors.CURRENT_HEADER,
    body_color: str = Colors.CURRENT_BODY,
)
```

#### Methods

- `set_row_count(count)`: Update number of visible rows
- `set_data(data)`: Set table content from list of tuples

---

### HistoryTable

Extends ProcessTable with timestamp column for historical records.

#### Methods

- `set_data(data)`: Set data with (name, value, cores, time) tuples

---

### MainWindow

Main application window with monitoring display.

#### Methods

- `_show_settings()`: Open settings dialog
- `_apply_settings()`: Apply configuration changes
- `_start_monitoring()`: Begin update timer
- `_toggle_pause()`: Pause/resume monitoring
- `_update()`: Refresh display with current data

#### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Esc` | Close window |
| `Space` | Toggle pause |

---

## UI Layout

```
┌─────────────────────────────────┐
│         Header Widget           │
│  Current: XX.X% | Peak: XX.X%   │
├─────────────────────────────────┤
│     Current Processes Label     │
├─────────────────────────────────┤
│  Process  │  Usage  │  Cores    │
│  ─────────────────────────────  │
│  Chrome   │  15.2%  │   1.2     │
│  VS Code  │  12.1%  │   0.8     │
│  ...      │  ...    │   ...     │
├─────────────────────────────────┤
│   Historical Peak Usage Label   │
├─────────────────────────────────┤
│  Process  │  Peak   │  Time     │
│  ─────────────────────────────  │
│  Chrome   │  45.2%  │  14:23    │
│  ...      │  ...    │  ...      │
├─────────────────────────────────┤
│        [Pause] [Settings]       │
└─────────────────────────────────┘
```

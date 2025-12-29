# App Module

This folder contains the core application components for Process Monitor.

---

## Purpose

The `app` module provides all GUI and business logic components for the Process Monitor application, built with PySide6 (Qt6).

---

## Structure

```
📁 app/
  🐍 __init__.py        ← Package exports
  🐍 main_window.py     ← Main application window
  🐍 settings_dialog.py ← Configuration dialog
  🐍 monitor.py         ← Process monitoring logic
  🐍 styles.py          ← UI styling constants
```

---

## Components

| Component | Documentation | Description |
|-----------|---------------|-------------|
| MainWindow | [main_window.md](main_window.md) | Primary window with tables and controls |
| SettingsDialog | [settings_dialog.md](settings_dialog.md) | Configuration dialog |
| ProcessMonitor | [monitor.md](monitor.md) | psutil integration for data collection |
| Styles | [styles.md](styles.md) | Colors, fonts, dimensions |

---

## Architecture

```mermaid
flowchart TB
    subgraph APP["App Module"]
        MW[MainWindow]
        SD[SettingsDialog]
        PM[ProcessMonitor]
        ST[Styles]
    end

    main.py --> MW
    MW --> SD
    MW --> PM
    SD --> ST
    MW --> ST
    PM --> psutil[(psutil)]
```

---

## Data Flow

1. **Startup**: `main.py` creates `MainWindow`
2. **Configuration**: `SettingsDialog` collects user preferences
3. **Monitoring**: `ProcessMonitor` queries psutil at intervals
4. **Display**: Tables update with formatted data

---

## Usage

```python
from app import MainWindow

# Create and show
window = MainWindow()
window.show()
```

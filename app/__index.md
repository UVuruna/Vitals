# App Module

This folder contains every GUI and business-logic component of Process
Monitor, built with PySide6 (Qt6).

---

## Purpose

Vitals runs as a **desktop gadget**: up to three monitor windows
(CPU, Memory, Network), each a taskbar-less `Qt.Tool` window, fed by one
shared background collector thread and controlled through a single system
tray icon. Closing a window hides it and pauses its data collection; the
tray icon (or File > Exit) is the only way to actually quit.

---

## Structure

```
📁 app/
  🐍 __init__.py            ← Package exports
  🐍 main_window.py         ← BaseMonitorWindow, CPUWindow, MemoryWindow, NetworkWindow
  🐍 settings_dialog.py     ← InitialSettingsDialog, CPUSettingsDialog, MemorySettingsDialog, NetworkSettingsDialog
  🐍 monitor.py             ← SharedDataCollector, ProcessMonitor, NetworkMonitor, RollingWindow
  🐍 network_monitor.py     ← NetworkTracer (ETW kernel trace), get_link_speed_mbps
  🐍 color_management.py    ← ProcessColorManager (company hues + value color zones)
  🐍 persistence.py         ← last_setup.json load/save (atomic, corruption-safe), base/data path resolution
  🐍 tray.py                ← TrayController (single tray icon, gadget-mode shell identity)
  🐍 styles.py               ← Dark theme palette (Colors), dimensions, fonts, formatting helpers
  🐍 process_actions.py     ← Kill / set priority / open file location (live psutil operations)
  🐍 process_dialog.py      ← Kill-confirm and priority-selection dialogs
```

---

## Modules

| Module | Documentation | Description |
|--------|---------------|-------------|
| Main Window | [Main Window](main_window.md) | The three gadget windows and their shared base class |
| Settings Dialog | [Settings Dialog](settings_dialog.md) | Launcher and per-mode settings dialogs, color-scale widget, company legend |
| Monitor | [Monitor](monitor.md) | Background collector thread, per-mode monitors, rolling averages |
| Network Monitor | [Network Monitor](network_monitor.md) | ETW kernel trace for per-process network bytes |
| Color Management | [Color Management](color_management.md) | Company hue assignment and value-threshold color mapping |
| Persistence | [Persistence](persistence.md) | `last_setup.json` access point, bundled vs. writable paths |
| Tray Controller | [Tray Controller](tray.md) | Single tray icon — the app's shell identity in gadget mode |
| Styles | [Styles](styles.md) | Dark palette, dimensions, fonts, formatting functions |

`process_actions.py` and `process_dialog.py` have no separate module doc —
see their usage under [Main Window](main_window.md)'s Connections section.

---

## Data Flow

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    main["main.py"]

    subgraph WINDOWS["Monitor windows (Qt.Tool gadgets)"]
        CPU[CPUWindow]
        MEM[MemoryWindow]
        NET[NetworkWindow]
    end

    TRAY[TrayController]

    subgraph COLLECT["SharedDataCollector — QThread singleton"]
        PM_CPU[ProcessMonitor — CPU]
        PM_MEM[ProcessMonitor — Memory]
        NM[NetworkMonitor]
        NT[NetworkTracer]
    end

    subgraph SUPPORT["Shared services"]
        PCM[ProcessColorManager]
        PERSIST[(persistence.py)]
        STYLES[styles.py]
    end

    main --> WINDOWS
    main --> TRAY
    main --> COLLECT
    TRAY -->|show_from_tray / _hide_to_tray| WINDOWS
    WINDOWS -->|configure_*| COLLECT
    COLLECT -->|cpu/memory/network_data_ready| WINDOWS
    PM_CPU --> NtQSI[(NtQuerySystemInformation)]
    PM_MEM --> NtQSI
    NM --> NT
    NT --> ETW[(ETW kernel trace)]
    WINDOWS --> PCM
    WINDOWS --> PERSIST
    WINDOWS --> STYLES
    PCM --> PERSIST
```

1. **Startup** — `main.py` shows `InitialSettingsDialog`, creates the enabled
   windows, wires CPU/Memory as refresh-rate peers, and starts the one
   `SharedDataCollector` thread and one `TrayController`.
2. **Collection** — each tick, the collector makes a single bulk
   `NtQuerySystemInformation` call (CPU/Memory) and reads the ETW tracer's
   accumulated bytes (Network), then emits a data-ready signal per enabled mode.
3. **Display** — each window's `_on_data_ready()` fills its current/history/
   rolling tables, coloring cells via `ProcessColorManager`.
4. **Gadget lifecycle** — the windows are `Qt.Tool` gadgets (native title bar,
   normal move/resize) with no taskbar/Alt-Tab presence. Closing a window (its
   X, `Esc`, the tray checkbox, or the tray **Minimize** which drops all at
   once) only hides it — the collector keeps running, so peaks/history stay
   continuous. The tray icon's **double-click toggles** all windows (hides them
   if any is visible, else re-shows them all); the per-window checkbox brings a
   single one back via `show_from_tray()`. Exit (File menu or tray menu) is the
   only path to `QApplication.quit()`.

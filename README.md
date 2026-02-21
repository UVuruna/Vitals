# 🖥️ Process Monitor

> Real-time CPU and Memory usage monitoring for Windows — lightweight desktop gadget with company-based coloring and historical peak tracking.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔄 **Real-time Monitoring** | Live updates of CPU % and Memory per process |
| 🪟 **Dual Monitor Mode** | CPU and Memory monitors open as independent windows |
| 🎨 **Company Coloring** | Processes colored by company (Microsoft, Adobe, …) — hues distributed evenly across 360° |
| 📊 **Value Color Scale** | Usage % mapped to 5 color zones — separate scales for CPU and Memory |
| 🗂️ **Process Aggregation** | Groups sub-processes (all Chrome tabs → "Chrome") |
| 📈 **Historical Tracking** | Records peak usage with timestamps, auto-expires |
| 🧵 **Thread Count** | Parallel threads per process (CPU mode) |
| 💾 **Persistent Setup** | Last-used settings restored automatically on next launch |
| 🔁 **Pause / Resume** | Freeze the display without stopping collection |
| ↕️ **Resizable Panels** | Drag the splitter between current and history tables |

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install PySide6 psutil

# 2. Run
python main.py
```

---

## 🖱️ Usage

1. **Launch** — `python main.py` (or run the installed `PMUsage.exe`)
2. **Select monitors** — choose CPU, Memory, or both
3. **Adjust settings** — rows, refresh rate, retention time, memory unit, color thresholds
4. **Click "Start Monitoring"** — settings are saved and restored next launch

### ⌨️ Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Pause / Resume monitoring |
| `Esc` | Close settings dialog |

---

## ⚙️ Configuration

### Setup Dialog

| Setting | Range | Default | Description |
|---------|-------|---------|-------------|
| Monitor Mode | CPU / Memory / Both | CPU | Which monitors to open |
| Current processes | 1 – 15 | 7 | Rows in the current table |
| History records | 1 – 15 | 4 | Rows in the history table |
| Refresh rate | 500 – 5000 ms | 2000 ms | Data update interval |
| History retention | 10 – 360 min | 120 min | How long history records are kept |
| Memory unit | KB / MB / GB | MB | Unit for memory values |
| Color thresholds | 4 draggable handles | 3 / 8 / 20 / 40 % | Zone boundaries on the color scale |

Settings are saved to `config/last_setup.json` and loaded on next launch.

### Color Scale

The color bar shows 5 usage zones. Drag the 4 diamond handles to move zone boundaries:

```
 ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
 blue  green    yellow   orange       red
 0%    3%       8%       20%    40%   100%
       ◆        ◆        ◆      ◆
```

CPU and Memory maintain **independent** threshold sets — adjusting one doesn't affect the other.

### config/config.json

Edit to change default color zones:

```json
{
  "value_colors": {
    "ranges": [
      {"max_pct": 3,   "color": "#5B9BD5"},
      {"max_pct": 8,   "color": "#6AAF6A"},
      {"max_pct": 20,  "color": "#C8B040"},
      {"max_pct": 40,  "color": "#D4803A"},
      {"max_pct": 100, "color": "#C85555"}
    ]
  }
}
```

---

## 🎨 Company Coloring

Process names are colored by the company listed in each executable's PE version info (read via `version.dll`):

- 🟣 **Named company** — hue assigned dynamically: `hue = index / N × 360°`
  As new companies are discovered N grows and all hues shift, keeping them evenly spread.
- ⬜ **No company info** — fixed gray (`#999999`)

The **Company Legend** button (in CPU/Memory settings) shows which color belongs to which company and how many processes each has.

---

## 🏗️ Architecture

```mermaid
flowchart TB
    main["🚀 main.py"]

    subgraph UI["Windows"]
        CPU["🖥️ CPUWindow"]
        MEM["💾 MemoryWindow"]
    end

    subgraph COLLECT["Data Collection"]
        SDC["⚙️ SharedDataCollector\n(QThread singleton)"]
        PM1["ProcessMonitor\nCPU mode"]
        PM2["ProcessMonitor\nMemory mode"]
    end

    subgraph COLORS["Color Engine"]
        PCM["🎨 ProcessColorManager\n(singleton)"]
    end

    main -->|InitialSettingsDialog| UI
    main --> SDC
    SDC --> PM1
    SDC --> PM2
    PM1 -->|cpu_data_ready| CPU
    PM2 -->|memory_data_ready| MEM
    CPU --> PCM
    MEM --> PCM
    PM1 --> psutil[(psutil)]
    PM2 --> psutil
    PCM -->|CompanyName| ver["version.dll"]
```

### Data Flow

```mermaid
sequenceDiagram
    participant T as QTimer
    participant SDC as SharedDataCollector
    participant PM as ProcessMonitor
    participant W as CPUWindow / MemoryWindow
    participant PCM as ProcessColorManager

    T->>SDC: interval tick
    SDC->>PM: get_processes(limit)
    PM->>SDC: list[ProcessInfo]
    SDC->>W: cpu_data_ready / memory_data_ready
    W->>PCM: get_process_color(name)
    W->>PCM: get_value_color(pct, mode)
    PCM->>W: QColor
    W->>W: render table rows
```

---

## 📁 Project Structure

```
📁 PMUsage/
  🐍 main.py                ← Entry point
  📝 README.md              ← This file
  📝 CLAUDE.md              ← AI assistant guidance
  📁 app/
    📝 __index.md           ← App module overview
    🐍 main_window.py       ← CPUWindow, MemoryWindow
    🐍 settings_dialog.py   ← InitialSettingsDialog, CPUSettingsDialog, MemorySettingsDialog
    🐍 monitor.py           ← SharedDataCollector, ProcessMonitor
    🐍 color_management.py  ← ProcessColorManager (company hues + value color zones)
    🐍 styles.py            ← UI constants (colors, fonts, dimensions)
  📁 config/
    📄 config.json           ← Value color thresholds (editable)
    📄 last_setup.json       ← Last-used settings (auto-generated)
  📁 assets/
    🖼️ icon.ico             ← Application icon
    🖼️ icon.svg             ← SVG source
  📁 setup/
    🐍 build.py             ← Build orchestrator (PyInstaller + NSIS)
    🐍 create_cert.py       ← Self-signed certificate generator
    📄 installer.nsi         ← NSIS installer script
  📁 docs/
    📁 plans/               ← Historical implementation plans
```

---

## 🔧 Building from Source

```bash
# Full build (ICO → PyInstaller → sign → NSIS installer)
python setup/build.py
```

**Prerequisites:**
- `pip install pyinstaller pillow`
- [NSIS](https://nsis.sourceforge.io/) installed and on PATH
- Optional: run `python setup/create_cert.py` once for code signing

Output: `dist/PMUsage_Setup.exe`

---

## 📋 Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.11+ |
| PySide6 | ≥ 6.5.0 |
| psutil | ≥ 5.9.0 |
| Windows | 10 / 11 |

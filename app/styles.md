# Styles

**Script:** [styles.py (script)](styles.py)

---

## Purpose

Centralized UI styling constants including colors, fonts, dimensions, and default values. Also contains process name mapping logic.

---

## Connections

### Uses

- None (standalone constants)

### Used by

- [MainWindow](main_window.md) - UI styling
- [SettingsDialog](settings_dialog.md) - UI styling
- [ProcessMonitor](monitor.md) - Process name mapping

---

## Constants

### Colors

| Constant | Value | Usage |
|----------|-------|-------|
| `BACKGROUND` | #ECF5F9 | Window background |
| `CURRENT_HEADER` | #FFC6C6 | Current section header (red) |
| `CURRENT_BODY` | #FFE2E2 | Current section body (light red) |
| `HISTORY_HEADER` | #A2D2FF | History section header (blue) |
| `HISTORY_BODY` | #E2F1FF | History section body (light blue) |
| `TEXT_PRIMARY` | #060606 | Main text |
| `TEXT_SECONDARY` | #444444 | Secondary text |
| `ACCENT_CPU` | #FF6B6B | CPU accent color |
| `ACCENT_MEMORY` | #4ECDC4 | Memory accent color |

---

### Dimensions

| Constant | Value | Usage |
|----------|-------|-------|
| `WINDOW_WIDTH` | 500 | Main window width |
| `WINDOW_MIN_HEIGHT` | 400 | Minimum window height |
| `MARGIN` | 10 | Standard margin |
| `SPACING` | 8 | Widget spacing |
| `TABLE_ROW_HEIGHT` | 28 | Table row height |
| `HEADER_HEIGHT` | 50 | Header widget height |
| `SETTINGS_WIDTH` | 450 | Settings dialog width |
| `SETTINGS_HEIGHT` | 400 | Settings dialog height |

---

### Fonts

| Constant | Value |
|----------|-------|
| `FAMILY` | "Segoe UI" |
| `SIZE_HEADER` | 14 |
| `SIZE_BODY` | 11 |
| `SIZE_SMALL` | 10 |

---

### Defaults

Default application settings:

| Setting | Default |
|---------|---------|
| Current rows | 7 |
| History rows | 4 |
| Refresh rate | 2000 ms |
| Retention | 120 min |
| Memory unit | MB |

---

### Memory Units

```python
MEMORY_UNITS = {
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
}
```

---

## Functions

### get_process_display_name

Maps process names to display-friendly names.

```python
def get_process_display_name(name: str) -> str:
    """
    Convert process name to display-friendly name.

    Args:
        name: Original process name (e.g., "Code.exe")

    Returns:
        Display name (e.g., "Visual Studio Code")
    """
```

#### Mappings

| Prefix | Display Name |
|--------|--------------|
| Code | Visual Studio Code |
| logi | Logi Options+ |
| steam | Steam |
| nv | NVIDIA |
| msedge | Microsoft Edge |
| chrome | Chrome |
| firefox | Firefox |

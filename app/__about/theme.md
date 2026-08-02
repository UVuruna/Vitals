# Theme

**Script:** [Theme (script)](../theme.py) ·
**Flow:** [diagram](../__flow/theme.md)

## Purpose

The single source of truth for every color in Vitals, and the engine that
flips a **scope** between the Dark and Light palettes at runtime. Colors used
to live behind a frozen `Colors` dataclass read inside module-level
f-strings, which froze the dark palette at import and made a runtime flip
impossible. This module replaces that with a live lookup: every widget reads
`scope.palette` when it builds or rebuilds a stylesheet, and re-runs that
build when `scope.changed` fires.

Themes are per **scope**, never per app (owner 2026-07-26): each monitor
window owns its own `ThemeScope`, so the Day/Night switch in the CPU header
flips the CPU window alone. There is deliberately no global `theme()`
accessor — a widget may only ask "what is MY scope's theme?". Colors are
also computed, not enumerated (root Rule #19): one authored set of hues is
re-shaded per theme by `shade_for_theme()` rather than hand-authoring a
second light-mode table.

## Connections

### Uses
- [Persistence](persistence.md) — reads/writes each scope's theme choice in `last_setup.json`

### Used by
- [Styles](styles.md) — `Palette` as the type for `context_menu_style(palette)`
- [Color Management](color_management.md) — `THEMES`, `Palette`, `wheel_color()`, `shade_for_theme()`
- [Icons](icons.md) — `ThemeScope`, the type every `IconButton` binds to
- [Day/Night Switch](theme_switch.md) — the `ThemeScope` it renders and follows
- [Theme Transition (flow)](../__flow/transition.md) — `LIGHT`, `app_theme()`, `set_theme_everywhere()`, and each scope's `set_theme()`
- [Tray](tray.md) — `app_theme()`; restyles the tray menu on a global flip
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — every dialog binds to one scope at construction: `app_theme()` for the setup screen, `window_theme(key)` for a per-mode dialog
- [Windows (subfolder)](../windows/___windows.md) — each monitor window owns `window_theme(key)`; every restyled widget reads `scope.palette`
- `app/__init__.py` — re-exports `ThemeScope`, `app_theme`, `window_theme` as the package's public theme API

## Classes

### Palette
Frozen dataclass holding one complete theme. Two instances exist — `DARK`
and `LIGHT` — registered in `THEMES`. Groups: surfaces (`BACKGROUND`, `CARD`,
`HEADER`, `BORDER`, `SECTION_BG`), accent (`ACCENT`/`ACCENT_HOVER`), confirm
(`CONFIRM`/`CONFIRM_HOVER`), text (`TEXT` … `TEXT_DISABLED`), header icons
(`ICON`/`ICON_HOVER`), temperature (`TEMP_WARNING`/`TEMP_CRITICAL`), and the
process-coloring data tokens (`COMPANY_TOP`, `COMPANY_UNKNOWN`,
`HUE_SATURATION`, `HUE_LIGHTNESS`, `VALUE_LIGHTNESS`) — these last five live
on the palette rather than in [Color Management](color_management.md)
because they must flip with the theme.

### ThemeScope
`QObject` owning the palette of one surface. Reached through `app_theme()`
or `window_theme(key)`, never constructed directly.

- `palette`: the active `Palette`
- `name` / `is_dark()` / `next_name()`: the active theme name and its opposite
- `changed`: `Signal()`, emitted AFTER the palette swaps
- `set_theme(name)`: activates a theme, persists it to this scope's own
  `last_setup.json` slot, emits `changed`. A no-op if that theme is already
  active.

## Functions

| Function | Description |
|----------|--------------|
| `app_theme()` | The app-wide scope (tray, setup screen), created on first use. |
| `window_theme(key)` | The scope for one monitor window (`'cpu'` / `'memory'` / `'network'`), created on first use and kept for the app's lifetime. |
| `set_theme_everywhere(name)` | Force one theme on the app scope, every live window scope, AND the remembered choice of a window not open yet. See [flow](../__flow/theme.md). |
| `wheel_hue(slot, slots)` / `wheel_color(slot, slots, saturation, lightness)` | Hue / `QColor` for one slot of the company color wheel. |
| `shade_for_theme(color, palette)` | Re-shades an authored hue to `palette.VALUE_LIGHTNESS`, hue and saturation preserved. |

## Design Decisions

- **Live palette read, never a module constant.** A stylesheet built from a
  module-level f-string or a default argument (`color: str = Colors.TEXT`)
  evaluates once, at import — a runtime flip could never reach it. Colors are
  therefore always read as `scope.palette` inside a restyle method.
- **Scopes over a single global theme.** A global `theme()` accessor would
  make per-window themes inexpressible — any widget could reach the one
  active palette. It was removed outright (root Rule #6, no compatibility
  shim): every color call site was revisited and given the scope it belongs
  to.
- **The palette carries data tokens.** `COMPANY_TOP`, `COMPANY_UNKNOWN`,
  `HUE_*` and `VALUE_LIGHTNESS` are process-coloring inputs, but they must
  flip with the theme, so they live with the palette, not in
  [Color Management](color_management.md).
- **Persistence.** Each scope owns one slot: the app-wide theme is `theme`,
  a window's is `windows.<key>.theme`. A window with no theme of its own
  starts from the app-wide choice, so a fresh install opens every gadget in
  one look.

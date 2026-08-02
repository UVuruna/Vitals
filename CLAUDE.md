# CLAUDE.md — Vitals

Project guidance for Claude Code. **The monorepo constitution governs**: read
the root `CLAUDE.md` first, then load ONLY the rulebook your job needs via its
Router. Nothing universal is restated here — this file carries project FACTS
and project DELTAS, and may only tighten root rules, never loosen them.

| Your job this session | Read (monorepo root) |
|-----------------------|----------------------|
| Implement / fix | `rules/CODE.md` + the folder's `___folder.md` |
| Any GUI work | `rules/GUI.md` + `DESIGN.md` |
| Write documentation | `rules/DOCS.md` |
| Build / release | `rules/SHIP.md` |
| Split a god-file | `REFACTOR-GODFILES.md` |
| Plan / brainstorm | `rules/PLAN.md` |

Start here for the code itself: [Vitals README](README.md) →
[App (folder)](app/___app.md). Open decisions live in
[Open Questions](OPEN-QUESTIONS.md).

---

## Project Facts

- **Product:** Vitals (formerly PMUsage) — a lightweight Windows desktop gadget
  for real-time process monitoring: top N processes by CPU, Memory or Network
  usage, historical peaks with timestamps, rolling averages, CPU cores/threads
  per process. Minimal footprint, always visible without getting in the way.
- **Naming:** display name, local folder (`Gadgets/Vitals/`) and GitHub repo
  (`UVuruna/Vitals`) are all **Vitals** — PMUsage / ProcessMemoryUsage are
  historical only.
- **Stack:** Python 3.11+, PySide6 (Qt6), psutil.
- **Architecture:** up to three gadget windows (CPU, Memory, Network), each a
  taskbar-less `Qt.Tool` window built from the `BaseMonitorWindow`
  template-method base. ONE `SharedDataCollector` QThread feeds all of them —
  a single bulk `NtQuerySystemInformation` call per tick for CPU/Memory, an ETW
  kernel trace for Network. A single tray icon is the app's only shell identity
  and its **Exit** is the only way to quit.
- **Build:** PyInstaller (`--onedir`, `--uac-admin` — the ETW network trace
  needs elevation) + NSIS, Task Scheduler `/rl highest` autostart (a Registry
  `Run` entry is silently skipped for elevated apps).

## Package Map

```
📁 app/
  📁 collect/   ← data acquisition: Windows queries, per-mode stats, the collector thread
  📁 dialogs/   ← the setup screen, the three per-monitor dialogs, process dialogs
  📁 windows/   ← the three gadget windows and everything they are built from
  🐍 theme.py · styles.py · settings.py · persistence.py · icons.py ·
     theme_switch.py · transition.py · color_management.py ·
     process_actions.py · startup.py · tray.py · window_manager.py
```

Full breakdown: [App (folder)](app/___app.md).

---

## Project Deltas

These TIGHTEN the root rules for this codebase. Break one and the app looks
half-painted, or a one-window change leaks into the other two.

### Config home is split by kind

- **Colors → [Theme](app/__about/theme.md).** The `DARK` and `LIGHT` palettes
  are the single source of truth for every color, including the
  process-coloring tokens. Read them as `scope.palette` **at restyle time** —
  NEVER at import time (a module-level f-string or a default argument freezes
  the palette).
- **Everything else → [Styles](app/__about/styles.md)** (dimensions, switch
  geometry, fonts, defaults, unit tables, formatters) plus `config/config.json`
  (value-color hues and temperature trip points).
- Before hardcoding ANY value, ask which of the two it belongs in.

### The theme is PER SCOPE, never global (owner 2026-07-26)

Each monitor window owns a `ThemeScope` (`window_theme(key)`); the tray and the
setup screen use `app_theme()`. There is deliberately **no global `theme()`
accessor** — a widget must not be able to ask "what is the theme?", only "what
is MY window's theme?", or a one-window flip leaks into the others. A new
widget therefore **takes its scope (or a plain `Palette`) at construction**; it
never looks one up.

### Two flips, and coverage must match reach

A window header switch calls `flip_window_theme(scope, window)` — that window
alone, covered alone. The setup screen's switch calls `flip_app_theme()` —
`set_theme_everywhere()` behind covers on every visible window. Never call
`set_theme()` directly: the covered transition is what the owner asked for, and
a bare `set_theme()` shows the repaint cascade.

### Theme flips at runtime

Any widget that owns a stylesheet must rebuild it from `self._theme.palette` in
a restyle method connected to `self._theme.changed`. The per-mode dialogs are
exempt — they are modal and cannot see a flip — but the setup screen carries
its own switch, so `BaseSettingsDialog` widgets register a **restyler** instead
of styling once.

### Per-item colors need a re-render, not a restyle

Table cell brushes are invisible to stylesheets; `_apply_theme()` re-runs
`_render_data()` on the last tick so they change with the theme.

### `ProcessColorManager` is theme-LESS

It is a singleton shared by all three windows, so every getter takes the
`Palette` to answer for and it holds BOTH themes' shaded ranges at once. Do not
give it an "active theme".

### Compute color variants, never author them twice

One authored hue set is re-shaded per theme by `shade_for_theme()`. Do not add
a second light-mode color table.

### Placement thinks in FRAME coordinates

[Placement](app/windows/__about/placement.md) is the ONLY authority on where a
window may sit, and the only code that reasons about the FRAME rather than the
CLIENT rect. `Qt.Tool` windows have no taskbar button and no Alt-Tab entry, so
a window whose caption lands off-screen is unrecoverable by the user. Never
clamp a window anywhere else.

---

## Enforcement

Four guard tests run in the Claude Code hooks (`.claude/settings.json`):
`test_structure_law.py`, `test_config_sections.py`, `test_docs_coverage.py`,
`test_doc_links.py`. `python tests/run_guards.py` runs all four and exits 2 on
failure; `--fast` (the PostToolUse hook) runs the two source guards only.

- The RATCHET allowlist in `test_structure_law.py` is **empty** and may only
  shrink. Adding an entry needs the owner's explicit approval in that session.
- `CONFIG_FILES` in `test_config_sections.py` is seeded narrowly with
  `app/styles.py` and `app/theme.py`.
- Changing a file's documentation TIER means updating `test_docs_coverage.py`
  in the same commit.

See [Tests (folder)](tests/___tests.md).

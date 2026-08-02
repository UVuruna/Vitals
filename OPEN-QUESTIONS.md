# Open Questions — Vitals

Decisions an autonomous session made on its own that deserve the owner's yes or
no, and questions the code raised that only the owner can settle. Nothing here
blocks the app; everything here is a judgment call that was recorded instead of
being made silently.

Opened by the 2026-08-02 god-file split + docs migration session.

## Table of Contents

- [Awaiting a Decision](#awaiting)
- [Judgments Made and Why](#judgments)
- [Observations From Reading the Code](#observations)

---

<a id="awaiting"></a>

## Awaiting a Decision

### 1. `relaunch_elevated()` vs `main.py`'s AppUserModelID call

`app/windows/shell.py` now owns the two Windows shell integrations the windows
need (per-window taskbar icon, elevated relaunch). `main.py` still makes a
third call of the same family — `SetCurrentProcessExplicitAppUserModelID`
— inline at startup.

By placement law that line belongs beside its siblings in `shell.py`. It was
left where it is because the split's scope was the three god-files and
`main.py` is 95 lines. **Move it?** One line moves, one import is added.

### 2. `get_link_speed_mbps()` lives in the ETW tracer module

`app/collect/network_trace.py` is the ETW kernel-trace module, but it also
carries `get_link_speed_mbps()`, which is a plain psutil call with no ETW
involvement. Its two callers (`windows/network_window.py`,
`dialogs/setup_dialog.py`) both import it lazily.

It sits there for historical reasons. **Move it to its own tiny module, or
leave it?** Leaving it is defensible — "facts about the network interface" is
arguably one topic — but it is the only non-ETW thing in a 684-line ETW file.

### 3. QSS builders have two homes

`app/styles.py` holds `context_menu_style(palette)`; `app/dialogs/dialog_styles.py`
holds the seven dialog QSS builders. Both are "functions that take a palette
and return a stylesheet".

The split put the dialog builders next to their only consumers and left
`context_menu_style` in `styles.py` next to its consumers (the window's
process menu and the tray). **Acceptable, or should ALL QSS builders move to
one module** (e.g. a new `app/qss.py`)? Doing it now would have touched
`styles.py` and `tray.py`, which were outside the split's scope.

### 4. `config/config.json` is outside the Config Section Law guard

`tests/test_config_sections.py` is Python-AST based, so it cannot check a JSON
file. `config/config.json` carries the value-colour hues and the temperature
trip points — real config, unguarded.

**Worth a JSON-shaped check** (required keys, ascending thresholds, valid hex),
or is the file small enough to leave to review?

---

<a id="judgments"></a>

## Judgments Made and Why

These were decided during the session and need no answer unless you disagree.

| Judgment | Reasoning |
|----------|-----------|
| `CONFIG_FILES` seeded with only `app/styles.py` and `app/theme.py` | The root rule says seed narrowly. These two are the documented config homes (non-colour and colour). `app/color_management.py` was deliberately left OUT: it is mostly ranking/shading algorithm around small default tables. |
| `app/dialogs/mode_dialogs.py` keeps all three per-mode dialogs in one file | They are one family with one shape; each is under ~120 lines and the file is ~356 — far under the violation threshold. Splitting would have produced three near-identical 110-line files and three more docs. |
| `app/windows/base_window.py` stays whole at 886 lines | Inside the ~500–1,000 "smell" band, so the question was asked in writing (see its `__about/` doc). It is ONE responsibility — the monitor-window template. Every separable concern was extracted into the sibling modules; splitting further would mean mixins that fragment a single class. |
| `app/network_monitor.py` was renamed to `app/collect/network_trace.py` | It moved into `collect/` with the rest of the acquisition layer, where the name `network_monitor` would have collided with `NetworkMonitor`, the statistics class in `network_stats.py`. |
| `app/process_dialog.py` moved into `app/dialogs/` | It is a dialog; `dialogs/` is where dialogs live. |
| `scaled_font()` was added to `app/styles.py` | The window and the table factory both needed the (base size + FontScale offset) → QFont rule after the split. One rule, one home — the fonts section of the config file. |
| The RATCHET allowlist in `test_structure_law.py` is EMPTY | The split cleared every entry it would otherwise have needed. Nothing is owed. |

---

<a id="observations"></a>

## Observations From Reading the Code

Noticed while verifying documentation. **Reported, not fixed** — the split was
required to change no behavior.

1. **`peak_label` is never hidden again.** Switching the bottom table to
   "Rolling Average" leaves the "Peak: …" label visible (it is only ever set
   visible, in the page-0 branch). Pre-existing and preserved exactly; it may
   well be intentional, since the peak is still meaningful there.
2. **`MonitorStats.max_usage` / `max_usage_time` are never written.** Both
   fields exist on the dataclass but nothing assigns them; the peak actually
   shown comes from `ProcessMonitor._peak_buffer`. Dead fields, harmless.
3. **`MonitorMode.BOTH` is never used.** The enum member survives from before
   the window manager could open any combination of monitors.
4. **`ProcessMonitor.set_mode()` and `_refresh_rate_ms` have no live callers.**
   `set_mode` is never invoked (each monitor is constructed for one mode), and
   `_refresh_rate_ms` is stored by `set_refresh_rate()` but never read.
5. **Ten config constants have zero readers** (verified by grep across
   `app/`): `Dimensions.WINDOW_WIDTH`, `SETTINGS_WIDTH`, `SETTINGS_HEIGHT`,
   `MARGIN`, `SPACING`, `TABLE_ROW_HEIGHT`, `HEADER_HEIGHT`, and
   `Defaults.MAX_ROWS`, `CPU_THREADS`, `RAM_GB`. Dialogs call `resize()` with
   literal numbers instead, and the row spin boxes hardcode their 1–100 range.
   Either the constants or the literals should go — a config value nobody
   reads is a lie about where the value lives.

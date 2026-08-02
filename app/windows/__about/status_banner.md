# Status Banner

**Script:** [Status Banner (script)](../status_banner.py)

## Purpose

The one surface allowed to shout. `StatusBanner` is hidden until something is
actually wrong, and sits between the header and the data because a failure
that only whispers from a corner label reads as "no traffic", not "broken"
(root Rule #1) — the owner reported the Network window as "showing nothing"
when it was in fact refusing to trace and saying so in 10pt muted grey.

It shows a `TraceFailure`'s two lines (`reason`, `action`) and ONE remedy
button. Which remedy is offered is decided by the failure's CODE, not by
matching its text: relaunching elevated cannot fix "another instance
running", and retrying in-process can never gain Administrator.

## Connections

### Uses

- [Collect (subfolder)](../../collect/___collect.md) — `NEEDS_ADMIN` (`network_trace.py`), used to pick the button label
- [Theme](../../__about/theme.md) — `ThemeScope`, read in `apply_theme()`
- [Styles](../../__about/styles.md) — `FontScale`, `scaled_font`

### Used by

- [Base Window](base_window.md) — built once in `_setup_ui()`; driven by `show_status()`/`_apply_theme()`
- [Network Window](network_window.md) — the only mode that ever calls `show_status()` with a real failure (`data.error`), since it is the only mode whose data source (the ETW trace) can fail mid-run

## Classes

### StatusBanner (QWidget)
`code` (property) — the failure code currently on display, `""` when hidden.
`show_failure(failure)` — sets the reason/action text, picks "Restart as
administrator" vs. "Retry" from `failure.code`, and shows the banner.
`apply_theme()` — restyles from the owning window's palette; borrows the
existing `TEMP_CRITICAL` token for its border/text rather than introducing a
new color, so it follows the theme like everything else. The constructor
takes the owning window's `ThemeScope`, a font base, and an `on_action`
callback wired to the remedy button's `clicked` signal.

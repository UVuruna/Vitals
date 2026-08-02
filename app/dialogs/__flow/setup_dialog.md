# Setup Dialog — Flow

**About:** [description](../__about/setup_dialog.md)

## Layout Sketch

`_setup_ui()` stacks these zones top to bottom in one `QVBoxLayout`. The
Network Settings block is the only one that is conditionally visible.

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    subgraph TITLE["Title row"]
        T1["'Vitals' label"]
        T2["DayNightSwitch — GLOBAL flip"]
    end
    SUB["Subtitle — first-run vs. reopened-from-tray text"]
    subgraph MODE["Monitor Mode"]
        M1["CPU Usage button"]
        M2["Memory Usage button"]
        M3["Network button"]
        MH["hint: Select one or more monitors"]
    end
    subgraph DISPLAY["Display Settings"]
        D1["current / history rows"]
        D2["refresh rate slider"]
        D3["history retention slider"]
        D4["font size slider"]
    end
    subgraph MEMSET["Memory Settings"]
        ME1["Display unit combo (KB/MB/GB)"]
    end
    subgraph NETSET["Network Settings — visible only if Network checked"]
        N1["speed unit / sort combo"]
        N2["max download / upload spinboxes"]
    end
    START["Start with Windows toggle"]
    INFO["Detected: N CPU threads, N GB RAM"]
    BTN["Start Monitoring / Apply button"]

    TITLE --> SUB --> MODE --> DISPLAY --> MEMSET --> NETSET --> START --> INFO --> BTN
```

## Restyle Path

The setup screen is the only dialog in this folder that stays live after
construction — it registers for `self._theme.changed` because its own
switch can flip the app scope out from under it at any time.

```mermaid
flowchart LR
    A["user clicks the title-row DayNightSwitch"] --> B["flip_app_theme()"]
    B --> C["app_theme() scope emits changed"]
    C --> D["self._apply_theme() re-runs"]
    D --> E["every registered restyler re-applies its stylesheet"]
```

Pseudocode (language-neutral):

    ON WIDGET CREATION (label, combo, spinbox, slider, mode button, ...):
        builder = FUNCTION that renders this widget's QSS from a palette
        _register_restyle(-> widget.setStyleSheet(builder(self._theme.palette)))
        RUN restyle once immediately

    ON self._theme.changed:                      # only the setup screen connects this
        FOR EACH registered restyle IN _restylers_list():
            restyle()                             # rebuild that one widget's stylesheet

Two restylers are registered LAST, after the whole layout exists, because
they touch widgets built further down `_setup_ui()`:
`_update_mode_buttons` (the 3 mode buttons + the network section's
visibility) and `_update_startup_toggle` (the autostart toggle's ON/OFF
style). Both already existed as click handlers that repaint one widget for
its checked state — registering them as restylers reuses that method rather
than duplicating it.

## `_on_start()`

```mermaid
flowchart TB
    A["user clicks Start Monitoring / Apply"] --> B{"any mode button checked?"}
    B -- no --> Z["do nothing — button was disabled by _update_mode_buttons anyway"]
    B -- yes --> C["set_startup_registered(startup_toggle checked)"]
    C --> D["save_initial_settings(get_settings())"]
    D --> E["self.accept()"]
```

Pseudocode:

    ON start_btn clicked:
        IF no mode button is checked -> return   # guard; button is disabled anyway
        register or unregister Windows autostart to match the toggle
        save_initial_settings(get_settings())     # writes last_setup.json
        accept()                                  # closes the dialog with QDialog.Accepted

# Styles — Flow

**About:** [description](../__about/styles.md)

## The config section tree

`styles.py` is organized under named banner comments — root Rule #20's
"defined once, whole, in its section". Every non-color tunable value lives
under exactly one of these:

```
styles.py
  DIMENSIONS & GEOMETRY
    Dimensions      WINDOW_WIDTH, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
                     WINDOW_GAP, MIN_GRAB_WIDTH, MARGIN, SPACING,
                     TABLE_ROW_HEIGHT, HEADER_HEIGHT,
                     SETTINGS_WIDTH, SETTINGS_HEIGHT, MENU_LINE_CHARS
    Transition      FADE_MS, ICON_FRAC, ICON_MIN, ICON_MAX
    Switch          HEIGHT, ASPECT, KNOB_FACTOR, PAD, ANIM_MS,
                     HOVER_SCALE, SUN_CELL_SCALE

  FONTS
    Fonts           FAMILY, SIZE_HEADER, SIZE_BODY, SIZE_SMALL
    FontScale       TITLE, SECTION, SUBTITLE, BODY, SMALL, TINY, MIN_SIZE
                       .size(base, offset)        -> pt size
                       .row_height(base)           -> table row height
    scaled_font()   (base, offset, bold) -> QFont   [uses FontScale + Fonts]

  DEFAULT VALUES
    Defaults        CURRENT_ROWS, HISTORY_ROWS, MAX_ROWS, REFRESH_RATE_MS,
                     RETENTION_MINUTES, MEMORY_UNIT, NETWORK_UNIT,
                     FONT_SIZE, CPU_THREADS, RAM_GB,
                     NETWORK_MAX_DOWNLOAD_MBPS, NETWORK_MAX_UPLOAD_MBPS,
                     NETWORK_SORT_MODE, COLLECTOR_SLEEP_CHUNK_MS,
                     ROLLING_BUCKET_SECONDS

  UNIT TABLES & NAME ALIASES
    MEMORY_UNITS    {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
    NETWORK_UNITS   {"KB/s": 1024, "MB/s": 1024**2}
    PROCESS_ALIASES {prefix -> display name}   (Chrome, VS Code, Discord, ...)

  QSS BUILDERS
    context_menu_style(palette) -> str          [the one function of a Palette]

  FORMATTERS
    format_speed(bytes_per_sec, unit)
    format_bytes_total(total_bytes, unit)
    format_pct(value)
    get_process_display_name(name)              [@lru_cache, uses PROCESS_ALIASES]
```

Pseudocode for the two derived helpers that read more than one section:

```
FUNCTION scaled_font(base, offset, bold):
    size = MAX(FontScale.MIN_SIZE, base + offset)
    RETURN QFont(Fonts.FAMILY, size, bold ? Bold : Normal)

FUNCTION get_process_display_name(name):
    strip a trailing ".exe"
    FOR EACH (prefix, display_name) IN PROCESS_ALIASES:
        IF name starts with prefix (case-insensitive) -> RETURN display_name
    RETURN name unchanged
```

A value is added to exactly one section, defined once and whole — never
patched onto a class after its definition (root Rule #20's "defined once,
whole, in its section").

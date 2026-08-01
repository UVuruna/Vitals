"""The three gadget windows and everything they are built from.

`base_window.py` holds the template every monitor shares; `cpu_window.py`,
`memory_window.py` and `network_window.py` fill in only what differs per mode.
The rest of this package is what the template delegates to: window placement,
Windows shell integration, the process-table widgets and factory, the status
banner, layout persistence and the right-click process menu.
"""

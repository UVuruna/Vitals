"""Data acquisition layer — everything that produces monitor data.

Raw Windows queries (bulk process snapshot, HWiNFO sensors, the ETW network
trace) at the bottom, per-mode statistics on top, and one QThread collector
that ticks them all and emits to the windows. Nothing here imports Qt widgets
or knows a theme exists.
"""

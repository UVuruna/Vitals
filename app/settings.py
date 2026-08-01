"""The user's settings — one shared shape, four dataclasses.

`InitialSettings` is what the setup screen produces: every monitor's
configuration in one object. Each window then keeps a per-mode slice of it
(`CPUSettings`, `MemorySettings`, `NetworkSettings`) so its own settings
dialog can change one monitor without touching the others.

These live here, not beside a dialog, because three different layers read
them: the dialogs that edit them, the windows that apply them, and the window
manager that pushes one set into all three monitors.
"""

from dataclasses import dataclass

import psutil

from .persistence import load_last_setup, save_last_setup
from .styles import Defaults


# ══════════════════════════ SHARED SETUP SETTINGS ══════════════════════════

@dataclass
class InitialSettings:
    """Settings from initial dialog (launcher)."""
    cpu_enabled: bool = True
    memory_enabled: bool = False
    network_enabled: bool = False
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    memory_unit: str = Defaults.MEMORY_UNIT
    network_unit: str = Defaults.NETWORK_UNIT
    network_sort_mode: str = Defaults.NETWORK_SORT_MODE
    network_max_download_mbps: int = Defaults.NETWORK_MAX_DOWNLOAD_MBPS
    network_max_upload_mbps: int = Defaults.NETWORK_MAX_UPLOAD_MBPS
    font_size: int = Defaults.FONT_SIZE

    @property
    def cpu_threads(self) -> int:
        return psutil.cpu_count()

    @property
    def ram_gb(self) -> int:
        return round(psutil.virtual_memory().total / (1024 ** 3))

    @property
    def commit_limit_bytes(self) -> int:
        from .collect.system_query import get_commit_limit_bytes
        return get_commit_limit_bytes()


# ═══════════════════════════ PER-MODE SETTINGS ═══════════════════════════

@dataclass
class CPUSettings:
    """Settings for CPU window only."""
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    font_size: int = Defaults.FONT_SIZE


@dataclass
class MemorySettings:
    """Settings for Memory window only."""
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    memory_unit: str = Defaults.MEMORY_UNIT
    font_size: int = Defaults.FONT_SIZE


@dataclass
class NetworkSettings:
    """Settings for Network window only."""
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    network_unit: str = Defaults.NETWORK_UNIT
    sort_mode: str = Defaults.NETWORK_SORT_MODE
    max_download_mbps: int = Defaults.NETWORK_MAX_DOWNLOAD_MBPS
    max_upload_mbps: int = Defaults.NETWORK_MAX_UPLOAD_MBPS
    font_size: int = Defaults.FONT_SIZE


# ═════════════════════════════ PERSISTENCE ═════════════════════════════

def save_initial_settings(settings: InitialSettings) -> None:
    """Persist the last-used login settings to config/last_setup.json.

    The entry is UPDATED, never replaced: the same file also holds window
    layouts, themes, color thresholds and hue params.
    """
    data = load_last_setup()
    data.update({
        "cpu_enabled": settings.cpu_enabled,
        "memory_enabled": settings.memory_enabled,
        "network_enabled": settings.network_enabled,
        "current_rows": settings.current_rows,
        "history_rows": settings.history_rows,
        "refresh_rate_ms": settings.refresh_rate_ms,
        "retention_minutes": settings.retention_minutes,
        "memory_unit": settings.memory_unit,
        "network_unit": settings.network_unit,
        "network_sort_mode": settings.network_sort_mode,
        "network_max_download_mbps": settings.network_max_download_mbps,
        "network_max_upload_mbps": settings.network_max_upload_mbps,
        "font_size": settings.font_size,
    })
    save_last_setup(data)

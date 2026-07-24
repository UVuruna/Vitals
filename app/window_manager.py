"""
Window Manager — owns the three monitor windows.

Vitals can show a CPU, a Memory and a Network gadget. Which ones exist used
to be decided once, in `main.py`, from the setup screen's checkboxes — so
turning a monitor on later meant restarting the app.

This module makes that a runtime decision: it creates each window the first
time it is actually needed, shows and hides them, pushes one set of settings
into all of them, and keeps the CPU/Memory refresh-rate peering wired. That
is what lets the tray's **Settings** action reopen the setup screen and
configure all three monitors in one place (owner 2026-07-24).

A window is never destroyed once created — hiding is enough, and its monitor
keeps running so peaks and history stay continuous.
"""

from typing import Optional

from .main_window import BaseMonitorWindow, CPUWindow, MemoryWindow, NetworkWindow
from .monitor import SharedDataCollector
from .settings_dialog import InitialSettings

# Display order, and the InitialSettings flag that enables each mode
MODES: tuple[tuple[str, str], ...] = (
    ("cpu", "cpu_enabled"),
    ("memory", "memory_enabled"),
    ("network", "network_enabled"),
)

_WINDOW_TYPES = {
    "cpu": CPUWindow,
    "memory": MemoryWindow,
    "network": NetworkWindow,
}


class WindowManager:
    """Creates, shows and configures the monitor windows as one group."""

    def __init__(self, settings: InitialSettings, collector: SharedDataCollector):
        self._settings = settings
        self._collector = collector
        self._windows: dict[str, BaseMonitorWindow] = {}

    # --- access -------------------------------------------------------

    @property
    def settings(self) -> InitialSettings:
        """The settings every window was last configured with."""
        return self._settings

    def existing(self) -> list[BaseMonitorWindow]:
        """Every window created so far, in display order."""
        return [self._windows[key] for key, _flag in MODES if key in self._windows]

    def window(self, key: str) -> Optional[BaseMonitorWindow]:
        """The window for a mode, or None if it has never been needed."""
        return self._windows.get(key)

    def is_visible(self, key: str) -> bool:
        """Whether a mode's window exists and is currently on screen."""
        window = self._windows.get(key)
        return window is not None and window.isVisible()

    # --- lifecycle ----------------------------------------------------

    def _create(self, key: str) -> BaseMonitorWindow:
        """Build a mode's window and place it beside the ones already open."""
        window = _WINDOW_TYPES[key](self._settings, self._collector)
        previous = self.existing()
        if previous:
            last = previous[-1]
            window.move(last.x() + last.width() + 20, last.y())
        self._windows[key] = window
        self._link_peers()
        return window

    def _link_peers(self) -> None:
        """Wire CPU and Memory as refresh-rate peers once both exist.

        Both read from the same collector tick, so changing one window's rate
        has to move the other's with it.
        """
        cpu = self._windows.get("cpu")
        memory = self._windows.get("memory")
        if cpu is not None and memory is not None:
            cpu._peer_window = memory
            memory._peer_window = cpu

    def show(self, key: str) -> BaseMonitorWindow:
        """Show a mode's window, creating it on first use."""
        window = self._windows.get(key) or self._create(key)
        window.show_from_tray()
        return window

    def hide(self, key: str) -> None:
        """Hide a mode's window (its monitor keeps running)."""
        window = self._windows.get(key)
        if window is not None and window.isVisible():
            window._hide_to_tray()

    def set_visible(self, key: str, visible: bool) -> None:
        """Show or hide one mode's window."""
        if visible:
            self.show(key)
        else:
            self.hide(key)

    def hide_all(self) -> None:
        """Hide every visible window at once (the tray's Minimize)."""
        for window in self.existing():
            if window.isVisible():
                window._hide_to_tray()

    def show_all(self) -> None:
        """Re-show every window that already exists."""
        for window in self.existing():
            window.show_from_tray()

    def any_visible(self) -> bool:
        """Whether at least one monitor window is on screen."""
        return any(window.isVisible() for window in self.existing())

    # --- settings -----------------------------------------------------

    def apply_settings(self, settings: InitialSettings) -> None:
        """Adopt one settings object for every monitor, and match visibility.

        Called by the setup screen — at startup and again from the tray's
        Settings action. Each window's own per-mode settings dataclass is
        rebuilt from the shared values, so a change made in one place reaches
        all three monitors.
        """
        self._settings = settings
        for key, flag in MODES:
            enabled = getattr(settings, flag)
            if enabled:
                window = self._windows.get(key)
                if window is None:
                    self.show(key)
                    continue
                window.apply_shared_settings(settings)
                window.show_from_tray()
            else:
                self.hide(key)

    def prepare_exit(self) -> None:
        """Save every visible window's layout, then hide them all at once.

        Runs before the slow teardown so the whole app vanishes together
        instead of one window at a time.
        """
        for window in self.existing():
            if window.isVisible():
                window._save_window_layout()
            window.hide()

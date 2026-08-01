"""
System Tray Controller

Single tray icon representing the whole application (gadget mode).

The monitor windows use Qt.Tool, so they have no taskbar button and no
Alt-Tab entry — like desktop gadgets. This tray icon is the application's
only shell identity: its menu toggles each monitor window, opens the shared
**Settings** screen, and its **Exit** is the ONLY way to quit (a window's X
only hides it, and the menu bar that used to carry File > Exit is gone —
owner 2026-07-24).
"""

from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .dialogs.setup_dialog import InitialSettingsDialog
from .styles import context_menu_style
from .theme import app_theme
from .window_manager import MODES, WindowManager


class TrayController:
    """Owns the tray icon and its menu. Keep a reference for the app lifetime."""

    # Menu label per window-manager mode key
    _TITLES = {
        "cpu": "CPU",
        "memory": "Memory",
        "network": "Network",
    }

    def __init__(self, icon, manager: WindowManager):
        self._manager = manager
        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip("Vitals")

        self._menu = QMenu()
        self._apply_theme()
        app_theme().changed.connect(self._apply_theme)

        # One entry per mode, whether or not its window exists yet — checking
        # an unopened monitor creates it on the spot.
        self._window_actions = []
        for key, _flag in MODES:
            action = self._menu.addAction(self._TITLES[key])
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked, k=key: self._manager.set_visible(k, checked)
            )
            self._window_actions.append((action, key))

        self._menu.addSeparator()
        settings_action = self._menu.addAction("Settings")
        settings_action.triggered.connect(self._show_settings)
        reset_action = self._menu.addAction("Reset window positions")
        reset_action.setToolTip(
            "Bring every monitor window back to the centre of the screen"
        )
        reset_action.triggered.connect(self._manager.reset_positions)
        self._menu.addSeparator()
        minimize_action = self._menu.addAction("Minimize")
        minimize_action.triggered.connect(self._manager.hide_all)
        exit_action = self._menu.addAction("Exit")
        exit_action.triggered.connect(self._exit_app)

        self._menu.aboutToShow.connect(self._refresh_checks)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _apply_theme(self):
        """Restyle the tray menu for the APP theme (the tray outlives a flip).

        The tray belongs to no monitor window, so it follows the app-wide
        scope — the one the setup screen's global switch moves.
        """
        self._menu.setStyleSheet(context_menu_style(app_theme().palette))

    def _show_settings(self):
        """Open the shared setup screen — all three monitors in one place.

        The same dialog the app starts with, so there is one place that owns
        rows, refresh rate, retention, units and fonts for every window — and
        the GLOBAL Day/Night switch, which pushes one theme into all three.
        On accept the window manager pushes the values into each monitor and
        opens or hides windows to match the mode toggles.
        """
        dialog = InitialSettingsDialog(first_run=False)
        accepted = dialog.exec()
        if accepted:
            self._manager.apply_settings(dialog.get_settings())
        # Parentless, so nothing else will ever free it. Destroyed only AFTER
        # get_settings() is read — WA_DeleteOnClose would kill it inside
        # exec() and the read above would raise.
        dialog.deleteLater()

    def prepare_exit(self):
        """Hide the tray icon and every window at once, saving layouts first.

        Runs synchronously in the Exit click handler (and again via
        aboutToQuit — the second run is a no-op on already-hidden windows), so
        everything vanishes together before the slow teardown (collector stop,
        ETW session stop) begins.
        """
        self._tray.hide()
        self._manager.prepare_exit()

    def _exit_app(self):
        """Complete application exit: hide everything instantly, then quit."""
        self.prepare_exit()
        QApplication.instance().quit()

    def _refresh_checks(self):
        """Sync menu checkmarks with actual window visibility."""
        for action, key in self._window_actions:
            action.setChecked(self._manager.is_visible(key))

    def _on_activated(self, reason):
        """Double-click toggles all windows: hide them if any is visible, else show all."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self._manager.any_visible():
                self._manager.hide_all()
            else:
                self._manager.show_all()

"""NetworkWindow — the Network monitor gadget.

Only what Network mode does differently: it listens on `network_data_ready`,
replaces Usage with Download + Upload, has NO Σ total row (a sum of speeds is
not a meaningful "total"), puts the current upload and both cumulative totals
in the sensor row, and colors each direction against its own max speed.

It is also the only window that can be told its data source is unavailable:
when a tick carries a `TraceFailure`, the status banner goes up and the tables
are EMPTIED — leaving the last live rows next to a failure notice would read
as "these are current", which they are not.
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem

from ..collect.collector import SharedDataCollector
from ..collect.monitor_data import MonitorMode, NetworkMonitorData
from ..dialogs.mode_dialogs import NetworkSettingsDialog
from ..settings import InitialSettings, NetworkSettings
from ..styles import format_bytes_total, format_speed
from .base_window import BaseMonitorWindow


# ════════════════════════════ NETWORK WINDOW ════════════════════════════

class NetworkWindow(BaseMonitorWindow):
    """Network Monitor window."""

    def __init__(self, initial_settings: InitialSettings, collector: SharedDataCollector, parent=None):
        self._initial_settings = initial_settings
        self._collector = collector
        self._settings = self._settings_from_initial(initial_settings)
        # Max speed in bytes/sec for color scale percentage calculation
        self._max_dl_bytes = self._resolve_max_bytes(initial_settings.network_max_download_mbps)
        self._max_ul_bytes = self._resolve_max_bytes(initial_settings.network_max_upload_mbps)
        super().__init__(parent)

        # Connect to collector signal
        self._collector.network_data_ready.connect(self._on_data_ready)

        # Configure and start collector
        self._apply_settings()
        if not self._collector.isRunning():
            self._collector.start()

    def _settings_from_initial(self, initial: InitialSettings) -> NetworkSettings:
        return NetworkSettings(
            current_rows=initial.current_rows,
            history_rows=initial.history_rows,
            refresh_rate_ms=initial.refresh_rate_ms,
            retention_minutes=initial.retention_minutes,
            network_unit=initial.network_unit,
            sort_mode=initial.network_sort_mode,
            max_download_mbps=initial.network_max_download_mbps,
            max_upload_mbps=initial.network_max_upload_mbps,
            font_size=initial.font_size,
        )

    @staticmethod
    def _resolve_max_bytes(mbps: int) -> float:
        """Convert a max-speed setting (Mbps) to bytes/sec.

        0 means "auto" in the settings UI — resolve it to the detected link
        speed so color coding keeps working instead of silently turning off.
        """
        from ..collect.network_trace import get_link_speed_mbps
        resolved = mbps or get_link_speed_mbps()
        return resolved * 1_000_000 / 8

    def _get_mode(self) -> MonitorMode:
        return MonitorMode.NETWORK

    def _get_title(self) -> str:
        return "Network"

    def _get_mode_cols(self) -> str:
        return "net"

    def _get_window_key(self) -> str:
        return "network"

    def _has_total_row(self) -> bool:
        return False

    def _configure_collector(self):
        """Configure the shared collector for Network monitoring using current settings."""
        self._collector.configure_network(
            current_rows=self._settings.current_rows,
            history_rows=self._settings.history_rows,
            retention_minutes=self._settings.retention_minutes,
            refresh_rate_ms=self._settings.refresh_rate_ms,
            network_unit=self._settings.network_unit,
            sort_mode=self._settings.sort_mode,
            max_download_mbps=self._settings.max_download_mbps,
            max_upload_mbps=self._settings.max_upload_mbps,
        )

    def _create_settings_dialog(self):
        """Create the Network settings dialog, in this window's theme."""
        return NetworkSettingsDialog(self._theme, self, self._settings)

    def _store_settings(self, new_settings):
        """Store new settings and recompute max-speed color thresholds."""
        self._settings = new_settings
        self._max_dl_bytes = self._resolve_max_bytes(new_settings.max_download_mbps)
        self._max_ul_bytes = self._resolve_max_bytes(new_settings.max_upload_mbps)

    def _fill_net_cols(self, table, row, item, color_mgr):
        """Fill Network-specific columns: Download, Upload."""
        unit = self._settings.network_unit
        palette = self._theme.palette
        dl_str = format_speed(item.download, unit)
        dl_item = QTableWidgetItem(dl_str)
        if self._max_dl_bytes > 0:
            dl_pct = item.download / self._max_dl_bytes * 100
            dl_item.setForeground(color_mgr.get_value_color(dl_pct, "net_dl", palette))
        table.setItem(row, 2, dl_item)

        ul_str = format_speed(item.upload, unit)
        ul_item = QTableWidgetItem(ul_str)
        if self._max_ul_bytes > 0:
            ul_pct = item.upload / self._max_ul_bytes * 100
            ul_item.setForeground(color_mgr.get_value_color(ul_pct, "net_ul", palette))
        table.setItem(row, 3, ul_item)

    def _fill_net_history_cols(self, table, row, item, color_mgr):
        """Fill Network history columns: Download, Upload, Time."""
        self._fill_net_cols(table, row, item, color_mgr)
        table.setItem(row, 4, QTableWidgetItem(item.time_str))

    def _fill_net_rolling_cols(self, table, row, item, color_mgr):
        """Fill Network rolling columns: Download, Upload, Uptime."""
        self._fill_net_cols(table, row, item, color_mgr)
        uptime_min = round(item.uptime_seconds / 60)
        uptime_item = QTableWidgetItem(f"{uptime_min}m")
        if uptime_min >= self._settings.retention_minutes:
            uptime_item.setForeground(QColor(self._theme.palette.TEXT_MUTED))
        table.setItem(row, 4, uptime_item)

    def _render_data(self, data: NetworkMonitorData):
        """Draw one Network tick into the header and tables."""
        # Capture unavailable — raise the banner and clear the stale numbers.
        # The tables are emptied too: leaving the last live rows up next to a
        # failure notice reads as "these are current", which they are not.
        if data.error:
            self.show_status(data.error)
            self.total_label.setText("↓ --")
            self.peak_label.setText("Peak: --")
            self.sensor_widget.setVisible(False)
            for table in (self.current_table, self.history_table, self.rolling_table):
                for row in range(table.rowCount()):
                    for col in range(table.columnCount()):
                        table.setItem(row, col, QTableWidgetItem(""))
            return

        self.show_status(None)
        unit = self._settings.network_unit

        # Update header — big number = current download speed
        self.total_label.setText(f"↓ {format_speed(data.current_download, unit)}")
        self.peak_label.setText(data.peak_display)

        # Sensor row: Upload speed, Total Download, Total Upload
        value_style = f"color: {self._theme.palette.TEXT}; background: transparent;"
        self.sensor_widget.setVisible(True)
        self.sensor_name_labels[0].setText("Upload")
        self.sensor_value_labels[0].setText(f"↑ {format_speed(data.current_upload, unit)}")
        self.sensor_value_labels[0].setStyleSheet(value_style)

        self.sensor_name_labels[1].setText("Total ↓")
        self.sensor_value_labels[1].setText(format_bytes_total(data.cumulative_download, unit))
        self.sensor_value_labels[1].setStyleSheet(value_style)

        self.sensor_name_labels[2].setText("Total ↑")
        self.sensor_value_labels[2].setText(format_bytes_total(data.cumulative_upload, unit))
        self.sensor_value_labels[2].setStyleSheet(value_style)

        # Update current table (no total row for network)
        self._fill_process_rows(
            self.current_table, data.processes, self._fill_net_cols,
            limit=self.current_table.rowCount(),
        )

        # Update history table
        self._fill_process_rows(self.history_table, data.history, self._fill_net_history_cols)

        # Update rolling average table (dynamic row count)
        self.rolling_table.setRowCount(len(data.rolling_average))
        self._fill_process_rows(self.rolling_table, data.rolling_average, self._fill_net_rolling_cols)

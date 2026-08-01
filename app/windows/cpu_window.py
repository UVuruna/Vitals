"""CPUWindow — the CPU monitor gadget.

Everything shared lives in `BaseMonitorWindow`; this file is only what CPU
mode does differently: it listens on `cpu_data_ready`, adds the Parallel and
Threads columns, shows Temperature / Power / Electric from HWiNFO in the
sensor row, and colors usage against `cpu_threads * 100` (a 16-thread machine
tops out at 1600%, not 100%).
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem

from ..collect.collector import SharedDataCollector
from ..collect.monitor_data import MonitorData, MonitorMode
from ..dialogs.mode_dialogs import CPUSettingsDialog
from ..settings import CPUSettings, InitialSettings
from .base_window import BaseMonitorWindow


# ═══════════════════════════════ CPU WINDOW ═══════════════════════════════

class CPUWindow(BaseMonitorWindow):
    """CPU Monitor window."""

    def __init__(self, initial_settings: InitialSettings, collector: SharedDataCollector, parent=None):
        self._initial_settings = initial_settings
        self._collector = collector
        self._settings = self._settings_from_initial(initial_settings)
        super().__init__(parent)

        # Connect to collector signal
        self._collector.cpu_data_ready.connect(self._on_data_ready)

        # Configure and start collector
        self._apply_settings()
        if not self._collector.isRunning():
            self._collector.start()

    def _settings_from_initial(self, initial: InitialSettings) -> CPUSettings:
        return CPUSettings(
            current_rows=initial.current_rows,
            history_rows=initial.history_rows,
            refresh_rate_ms=initial.refresh_rate_ms,
            retention_minutes=initial.retention_minutes,
            font_size=initial.font_size,
        )

    def _get_mode(self) -> MonitorMode:
        return MonitorMode.CPU

    def _get_title(self) -> str:
        return "CPU"

    def _get_mode_cols(self) -> str:
        return "cpu"

    def _get_window_key(self) -> str:
        return "cpu"

    def _configure_collector(self):
        """Configure the shared collector for CPU monitoring using current settings."""
        self._collector.configure_cpu(
            cpu_threads=self._initial_settings.cpu_threads,
            ram_gb=self._initial_settings.ram_gb,
            current_rows=self._settings.current_rows,
            history_rows=self._settings.history_rows,
            retention_minutes=self._settings.retention_minutes,
            refresh_rate_ms=self._settings.refresh_rate_ms,
        )

    def _create_settings_dialog(self):
        """Create the CPU settings dialog, in this window's theme."""
        return CPUSettingsDialog(self._theme, self, self._settings)

    def _fill_cpu_cols(self, table, row, item, color_mgr):
        """Fill CPU-specific columns: Usage, Count, Threads."""
        monitor = self._collector.cpu_monitor
        value_str = monitor.format_value(item.value, "MB") if monitor else f"{item.value:.0f}"
        value_item = QTableWidgetItem(value_str)
        if monitor:
            pct = item.value / (monitor.cpu_threads * 100) * 100
            value_item.setForeground(
                color_mgr.get_value_color(pct, "cpu", self._theme.palette)
            )
        table.setItem(row, 2, value_item)
        table.setItem(row, 3, QTableWidgetItem(str(item.count)))
        table.setItem(row, 4, QTableWidgetItem(str(item.threads) if item.threads > 0 else ""))

    def _fill_cpu_history_cols(self, table, row, item, color_mgr):
        """Fill CPU history columns: Usage, Count, Threads, Time."""
        self._fill_cpu_cols(table, row, item, color_mgr)
        table.setItem(row, 5, QTableWidgetItem(item.time_str))

    def _fill_cpu_rolling_cols(self, table, row, item, color_mgr):
        """Fill CPU rolling columns: Usage, Count, Threads, Uptime."""
        self._fill_cpu_cols(table, row, item, color_mgr)
        uptime_min = round(item.uptime_seconds / 60)
        uptime_item = QTableWidgetItem(f"{uptime_min}m")
        if uptime_min >= self._settings.retention_minutes:
            uptime_item.setForeground(QColor(self._theme.palette.TEXT_MUTED))
        table.setItem(row, 5, uptime_item)

    def _render_data(self, data: MonitorData):
        """Draw one CPU tick into the header and tables."""
        monitor = self._collector.cpu_monitor

        # Update header
        self.total_label.setText(data.total_display)
        self.peak_label.setText(data.max_display)

        # Get HWiNFO sensor data
        hwinfo = data.hwinfo

        # CPU mode: Temperature, Power, Electric
        cpu_has_data = any([hwinfo.cpu_tctl, hwinfo.cpu_power, hwinfo.cpu_edc])
        self.sensor_widget.setVisible(cpu_has_data)
        if cpu_has_data:
            sensor_names = ["Temperature", "Power", "Electric"]
            sensor_data = [
                (f"{hwinfo.cpu_tctl:.1f}°C", hwinfo.cpu_tctl) if hwinfo.cpu_tctl else ("—", None),
                (f"{hwinfo.cpu_power:.1f} W", None) if hwinfo.cpu_power else ("—", None),
                (f"{hwinfo.cpu_edc:.1f} A", None) if hwinfo.cpu_edc else ("—", None),
            ]
            for i, (name, (value_text, temp_val)) in enumerate(zip(sensor_names, sensor_data)):
                self.sensor_name_labels[i].setText(name)
                self.sensor_value_labels[i].setText(value_text)
                self.sensor_value_labels[i].setStyleSheet(
                    f"color: {self._get_temp_color(temp_val)}; background: transparent;"
                )

        # Update current table
        total_row = self.current_table.rowCount() - 1
        color_mgr = self._fill_process_rows(
            self.current_table, data.processes, self._fill_cpu_cols, limit=total_row)

        # Fill Σ total row
        totals = data.process_totals
        self.current_table.setItem(total_row, 0, self._make_total_item("Σ"))
        self.current_table.setItem(total_row, 1, self._make_total_item("Total"))
        usage_str = monitor.format_value(totals.value, "MB") if monitor else f"{totals.value:.0f}"
        usage_item = self._make_total_item(usage_str)
        if monitor:
            pct = totals.value / (monitor.cpu_threads * 100) * 100
            usage_item.setForeground(
                color_mgr.get_value_color(pct, "cpu_all", self._theme.palette)
            )
        self.current_table.setItem(total_row, 2, usage_item)
        self.current_table.setItem(total_row, 3, self._make_total_item(str(totals.count)))
        self.current_table.setItem(total_row, 4, self._make_total_item(str(totals.threads) if totals.threads > 0 else ""))

        # Update history table
        self._fill_process_rows(self.history_table, data.history, self._fill_cpu_history_cols)

        # Update rolling average table (dynamic row count)
        self.rolling_table.setRowCount(len(data.rolling_average))
        self._fill_process_rows(self.rolling_table, data.rolling_average, self._fill_cpu_rolling_cols)

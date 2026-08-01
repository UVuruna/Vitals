"""MemoryWindow — the Memory monitor gadget.

Only what Memory mode does differently: it listens on `memory_data_ready`,
adds the Commit column, shows Committed / DRAM Read / DRAM Write from HWiNFO,
and colors two independent scales — working set against total RAM, commit
against the system commit limit.
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem

from ..collect.collector import SharedDataCollector
from ..collect.monitor_data import MonitorData, MonitorMode
from ..dialogs.mode_dialogs import MemorySettingsDialog
from ..settings import InitialSettings, MemorySettings
from .base_window import BaseMonitorWindow


# ═════════════════════════════ MEMORY WINDOW ═════════════════════════════

class MemoryWindow(BaseMonitorWindow):
    """Memory Monitor window."""

    def __init__(self, initial_settings: InitialSettings, collector: SharedDataCollector, parent=None):
        self._initial_settings = initial_settings
        self._collector = collector
        self._settings = self._settings_from_initial(initial_settings)
        self._commit_limit_bytes: int = initial_settings.commit_limit_bytes
        super().__init__(parent)

        # Connect to collector signal
        self._collector.memory_data_ready.connect(self._on_data_ready)

        # Configure and start collector
        self._apply_settings()
        if not self._collector.isRunning():
            self._collector.start()

    def _settings_from_initial(self, initial: InitialSettings) -> MemorySettings:
        return MemorySettings(
            current_rows=initial.current_rows,
            history_rows=initial.history_rows,
            refresh_rate_ms=initial.refresh_rate_ms,
            retention_minutes=initial.retention_minutes,
            memory_unit=initial.memory_unit,
            font_size=initial.font_size,
        )

    def _get_mode(self) -> MonitorMode:
        return MonitorMode.MEMORY

    def _get_title(self) -> str:
        return "Memory"

    def _get_mode_cols(self) -> str:
        return "mem"

    def _get_window_key(self) -> str:
        return "memory"

    def _configure_collector(self):
        """Configure the shared collector for Memory monitoring using current settings."""
        self._collector.configure_memory(
            cpu_threads=self._initial_settings.cpu_threads,
            ram_gb=self._initial_settings.ram_gb,
            current_rows=self._settings.current_rows,
            history_rows=self._settings.history_rows,
            retention_minutes=self._settings.retention_minutes,
            refresh_rate_ms=self._settings.refresh_rate_ms,
            memory_unit=self._settings.memory_unit,
        )

    def _create_settings_dialog(self):
        """Create the Memory settings dialog, in this window's theme."""
        return MemorySettingsDialog(self._theme, self, self._settings)

    def _fill_memory_cols(self, table, row, item, color_mgr):
        """Fill Memory-specific columns: Usage, Commit."""
        monitor = self._collector.memory_monitor
        unit = self._settings.memory_unit
        palette = self._theme.palette
        value_str = monitor.format_value(item.value, unit) if monitor else f"{item.value:.0f}"
        value_item = QTableWidgetItem(value_str)
        if monitor:
            pct = item.value / monitor.ram_bytes * 100
            value_item.setForeground(color_mgr.get_value_color(pct, "memory", palette))
        table.setItem(row, 2, value_item)
        commit_str = monitor.format_value(item.vms, unit) if monitor else ""
        commit_item = QTableWidgetItem(commit_str)
        if monitor and self._commit_limit_bytes > 0:
            commit_pct = item.vms / self._commit_limit_bytes * 100
            commit_item.setForeground(
                color_mgr.get_value_color(commit_pct, "memory_total", palette)
            )
        table.setItem(row, 3, commit_item)

    def _fill_memory_history_cols(self, table, row, item, color_mgr):
        """Fill Memory history columns: Usage, Commit, Time."""
        self._fill_memory_cols(table, row, item, color_mgr)
        table.setItem(row, 4, QTableWidgetItem(item.time_str))

    def _fill_memory_rolling_cols(self, table, row, item, color_mgr):
        """Fill Memory rolling columns: Usage, Commit, Uptime."""
        self._fill_memory_cols(table, row, item, color_mgr)
        uptime_min = round(item.uptime_seconds / 60)
        uptime_item = QTableWidgetItem(f"{uptime_min}m")
        if uptime_min >= self._settings.retention_minutes:
            uptime_item.setForeground(QColor(self._theme.palette.TEXT_MUTED))
        table.setItem(row, 4, uptime_item)

    def _render_data(self, data: MonitorData):
        """Draw one Memory tick into the header and tables."""
        monitor = self._collector.memory_monitor
        unit = self._settings.memory_unit

        # Update header
        self.total_label.setText(data.total_display)
        self.peak_label.setText(data.max_display)

        # Get HWiNFO sensor data
        hwinfo = data.hwinfo

        # Memory mode: Committed, Read, Write
        mem_has_data = any([hwinfo.virt_committed, hwinfo.dram_read, hwinfo.dram_write])
        self.sensor_widget.setVisible(mem_has_data)
        if mem_has_data:
            committed_str = (
                monitor.format_value(hwinfo.virt_committed, unit)
                if (monitor and hwinfo.virt_committed)
                else "—"
            )
            sensor_names = ["Committed", "Read", "Write"]
            sensor_values = [
                committed_str,
                f"{hwinfo.dram_read:,.0f} MB/s" if hwinfo.dram_read else "—",
                f"{hwinfo.dram_write:,.0f} MB/s" if hwinfo.dram_write else "—",
            ]
            text_color = self._theme.palette.TEXT
            for i, (name, value_text) in enumerate(zip(sensor_names, sensor_values)):
                self.sensor_name_labels[i].setText(name)
                self.sensor_value_labels[i].setText(value_text)
                self.sensor_value_labels[i].setStyleSheet(f"color: {text_color}; background: transparent;")

        # Update current table
        total_row = self.current_table.rowCount() - 1
        color_mgr = self._fill_process_rows(
            self.current_table, data.processes, self._fill_memory_cols, limit=total_row)

        # Fill Σ total row
        totals = data.process_totals
        self.current_table.setItem(total_row, 0, self._make_total_item("Σ"))
        self.current_table.setItem(total_row, 1, self._make_total_item("Total"))
        usage_str = monitor.format_value(totals.value, unit) if monitor else f"{totals.value:.0f}"
        usage_item = self._make_total_item(usage_str)
        palette = self._theme.palette
        if monitor:
            pct = totals.value / monitor.ram_bytes * 100
            usage_item.setForeground(color_mgr.get_value_color(pct, "memory_all", palette))
        self.current_table.setItem(total_row, 2, usage_item)
        total_commit_str = monitor.format_value(totals.vms, unit) if monitor else ""
        total_commit_item = self._make_total_item(total_commit_str)
        if monitor and self._commit_limit_bytes > 0:
            total_commit_pct = totals.vms / self._commit_limit_bytes * 100
            total_commit_item.setForeground(
                color_mgr.get_value_color(total_commit_pct, "memory_all_total", palette)
            )
        self.current_table.setItem(total_row, 3, total_commit_item)

        # Update history table
        self._fill_process_rows(self.history_table, data.history, self._fill_memory_history_cols)

        # Update rolling average table (dynamic row count)
        self.rolling_table.setRowCount(len(data.rolling_average))
        self._fill_process_rows(self.rolling_table, data.rolling_average, self._fill_memory_rolling_cols)

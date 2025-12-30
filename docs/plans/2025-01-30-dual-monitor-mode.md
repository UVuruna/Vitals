# Dual Monitor Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow selecting both CPU and Memory monitors simultaneously, opening two independent windows with centralized data collection.

**Architecture:** Initial settings dialog uses checkboxes (not radio) for mode selection. When both selected, two MainWindow instances open. A SharedDataCollector singleton collects psutil data once per interval and distributes to all windows. Each window has its own simplified settings dialog.

**Tech Stack:** Python 3.11+, PySide6, psutil

---

## Task 1: Add MonitorMode.BOTH to Enum

**Files:**
- Modify: `app/monitor.py:236-241`

**Step 1: Update MonitorMode enum**

```python
class MonitorMode(Enum):
    """Monitoring mode selection."""

    CPU = auto()
    MEMORY = auto()
    BOTH = auto()  # New: opens both CPU and Memory windows
```

**Step 2: Commit**

```bash
git add app/monitor.py
git commit -m "feat: add BOTH option to MonitorMode enum"
```

---

## Task 2: Create SharedDataCollector Singleton

**Files:**
- Modify: `app/monitor.py` (add after line 691)

**Step 1: Add SharedDataCollector class**

```python
class SharedDataCollector(QThread):
    """
    Singleton that collects process data once and distributes to multiple windows.

    When only one window is open, behaves like MonitorWorker.
    When both CPU and Memory windows are open, collects data once per interval
    and emits to both, reducing psutil calls by 50%.
    """

    cpu_data_ready = Signal(MonitorData)
    memory_data_ready = Signal(MonitorData)

    _instance: Optional['SharedDataCollector'] = None
    _lock = QMutex()

    def __new__(cls, parent=None):
        """Singleton pattern."""
        with QMutexLocker(cls._lock):
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, parent=None):
        if self._initialized:
            return
        super().__init__(parent)
        self._initialized = True

        self._cpu_monitor: Optional[ProcessMonitor] = None
        self._memory_monitor: Optional[ProcessMonitor] = None
        self._running = False
        self._interval_ms = 2000
        self._mutex = QMutex()

        # Settings per mode
        self._cpu_settings: Optional[dict] = None
        self._memory_settings: Optional[dict] = None

        # Subscribers
        self._cpu_enabled = False
        self._memory_enabled = False

    def configure_cpu(
        self,
        cpu_threads: int,
        ram_gb: int,
        current_rows: int,
        history_rows: int,
        retention_minutes: int,
        refresh_rate_ms: int,
    ):
        """Configure CPU monitoring."""
        with QMutexLocker(self._mutex):
            self._cpu_settings = {
                'current_rows': current_rows,
                'history_rows': history_rows,
            }
            if self._cpu_monitor is None:
                self._cpu_monitor = ProcessMonitor(
                    mode=MonitorMode.CPU,
                    cpu_threads=cpu_threads,
                    ram_gb=ram_gb,
                )
            self._cpu_monitor.set_history_settings(history_rows, retention_minutes)
            self._interval_ms = min(self._interval_ms, refresh_rate_ms)
            self._cpu_enabled = True

    def configure_memory(
        self,
        cpu_threads: int,
        ram_gb: int,
        current_rows: int,
        history_rows: int,
        retention_minutes: int,
        refresh_rate_ms: int,
        memory_unit: str,
    ):
        """Configure Memory monitoring."""
        with QMutexLocker(self._mutex):
            self._memory_settings = {
                'current_rows': current_rows,
                'history_rows': history_rows,
                'memory_unit': memory_unit,
            }
            if self._memory_monitor is None:
                self._memory_monitor = ProcessMonitor(
                    mode=MonitorMode.MEMORY,
                    cpu_threads=cpu_threads,
                    ram_gb=ram_gb,
                )
            self._memory_monitor.set_history_settings(history_rows, retention_minutes)
            self._interval_ms = min(self._interval_ms, refresh_rate_ms)
            self._memory_enabled = True

    def disable_cpu(self):
        """Disable CPU monitoring."""
        with QMutexLocker(self._mutex):
            self._cpu_enabled = False
            if not self._memory_enabled:
                self.stop()

    def disable_memory(self):
        """Disable Memory monitoring."""
        with QMutexLocker(self._mutex):
            self._memory_enabled = False
            if not self._cpu_enabled:
                self.stop()

    def run(self):
        """Main collector loop - collects once, emits to all subscribers."""
        self._running = True

        while self._running:
            with QMutexLocker(self._mutex):
                hwinfo = HWiNFOData()
                if self._cpu_monitor:
                    hwinfo = self._cpu_monitor.get_hwinfo_data()

                # Collect CPU data if enabled
                if self._cpu_enabled and self._cpu_monitor and self._cpu_settings:
                    processes = self._cpu_monitor.get_processes(self._cpu_settings['current_rows'])
                    self._cpu_monitor.update_history(processes)
                    history = self._cpu_monitor.get_history()

                    data = MonitorData(
                        processes=processes,
                        history=history,
                        total_display=self._cpu_monitor.get_total_display("MB"),
                        max_display=self._cpu_monitor.get_max_display("MB"),
                        hwinfo=hwinfo,
                        stats=self._cpu_monitor.stats,
                    )
                    self.cpu_data_ready.emit(data)

                # Collect Memory data if enabled
                if self._memory_enabled and self._memory_monitor and self._memory_settings:
                    unit = self._memory_settings.get('memory_unit', 'MB')
                    processes = self._memory_monitor.get_processes(self._memory_settings['current_rows'])
                    self._memory_monitor.update_history(processes)
                    history = self._memory_monitor.get_history()

                    data = MonitorData(
                        processes=processes,
                        history=history,
                        total_display=self._memory_monitor.get_total_display(unit),
                        max_display=self._memory_monitor.get_max_display(unit),
                        hwinfo=hwinfo,
                        stats=self._memory_monitor.stats,
                    )
                    self.memory_data_ready.emit(data)

            self.msleep(self._interval_ms)

    def stop(self):
        """Stop the collector."""
        self._running = False
        self.wait(2000)

    @property
    def cpu_monitor(self) -> Optional[ProcessMonitor]:
        """Get CPU monitor instance."""
        return self._cpu_monitor

    @property
    def memory_monitor(self) -> Optional[ProcessMonitor]:
        """Get Memory monitor instance."""
        return self._memory_monitor

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing)."""
        with QMutexLocker(cls._lock):
            if cls._instance is not None:
                cls._instance.stop()
                cls._instance = None
```

**Step 2: Commit**

```bash
git add app/monitor.py
git commit -m "feat: add SharedDataCollector singleton for centralized data collection"
```

---

## Task 3: Create InitialSettingsDialog with Checkboxes

**Files:**
- Modify: `app/settings_dialog.py`

**Step 1: Add InitialSettings dataclass after MonitorSettings**

```python
@dataclass
class InitialSettings:
    """Settings from initial dialog (launcher)."""
    cpu_enabled: bool = True
    memory_enabled: bool = False
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    memory_unit: str = Defaults.MEMORY_UNIT

    @property
    def cpu_threads(self) -> int:
        return psutil.cpu_count() or 8

    @property
    def ram_gb(self) -> int:
        return round(psutil.virtual_memory().total / (1024 ** 3))
```

**Step 2: Create InitialSettingsDialog class (add after SettingsDialog)**

```python
class InitialSettingsDialog(QDialog):
    """Initial settings dialog with checkbox mode selection."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Process Monitor - Setup")
        self.setFixedSize(480, 580)

        # Set window icon
        icon_path = get_base_path() / "assets" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#2a2a3e"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#3a3a4e"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#e94560"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._setup_ui()

    def _make_label(self, text: str, size: int = 12, bold: bool = False, color: str = "#ffffff") -> QLabel:
        """Create a styled label."""
        label = QLabel(text)
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        label.setFont(QFont("Segoe UI", size, weight))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        return label

    def _make_combo(self, items: list, default: str, width: int = 100) -> QComboBox:
        """Create a styled combo box."""
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentText(default)
        combo.setFont(QFont("Segoe UI", 11))
        combo.setFixedWidth(width)
        combo.setFixedHeight(32)
        combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a4e;
                color: #ffffff;
                border: 1px solid #4a4a5e;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox::down-arrow {
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #3a3a4e;
                color: #ffffff;
                selection-background-color: #e94560;
            }
        """)
        return combo

    def _setup_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        # Title
        title = self._make_label("Process Monitor", 20, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = self._make_label("Select monitors to open", 10, color="#888888")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(12)

        # === Monitor Mode (Checkboxes) ===
        layout.addWidget(self._make_label("Monitor Mode", 12, bold=True))

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)

        self.cpu_btn = QPushButton("CPU Usage")
        self.cpu_btn.setFont(QFont("Segoe UI", 11))
        self.cpu_btn.setFixedHeight(36)
        self.cpu_btn.setCheckable(True)
        self.cpu_btn.setChecked(True)
        self.cpu_btn.clicked.connect(self._update_mode_buttons)
        mode_row.addWidget(self.cpu_btn)

        self.mem_btn = QPushButton("Memory Usage")
        self.mem_btn.setFont(QFont("Segoe UI", 11))
        self.mem_btn.setFixedHeight(36)
        self.mem_btn.setCheckable(True)
        self.mem_btn.setChecked(False)
        self.mem_btn.clicked.connect(self._update_mode_buttons)
        mode_row.addWidget(self.mem_btn)

        self._update_mode_buttons()
        layout.addLayout(mode_row)

        # Hint text
        hint = self._make_label("Select one or both monitors", 9, color="#666666")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        layout.addSpacing(8)

        # === Display Settings ===
        layout.addWidget(self._make_label("Display Settings", 12, bold=True))

        # Current processes
        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_combo = self._make_combo([str(i) for i in range(1, 16)], str(Defaults.CURRENT_ROWS))
        row1.addWidget(self.current_combo)
        layout.addLayout(row1)

        # History records
        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_combo = self._make_combo([str(i) for i in range(1, 16)], str(Defaults.HISTORY_ROWS))
        row2.addWidget(self.history_combo)
        layout.addLayout(row2)

        # Refresh rate
        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("Refresh rate:", 11, color="#aaaaaa"))
        row3.addStretch()
        self.refresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.refresh_slider.setRange(5, 50)
        self.refresh_slider.setValue(Defaults.REFRESH_RATE_MS // 100)
        self.refresh_slider.setFixedWidth(140)
        self.refresh_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row3.addWidget(self.refresh_slider)
        self.refresh_label = self._make_label(f"{Defaults.REFRESH_RATE_MS} ms", 11)
        self.refresh_label.setFixedWidth(65)
        self.refresh_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.refresh_slider.valueChanged.connect(lambda v: self.refresh_label.setText(f"{v * 100} ms"))
        row3.addWidget(self.refresh_label)
        layout.addLayout(row3)

        # History retention
        row4 = QHBoxLayout()
        row4.addWidget(self._make_label("History retention:", 11, color="#aaaaaa"))
        row4.addStretch()
        self.retention_slider = QSlider(Qt.Orientation.Horizontal)
        self.retention_slider.setRange(10, 360)
        self.retention_slider.setValue(Defaults.RETENTION_MINUTES)
        self.retention_slider.setFixedWidth(140)
        self.retention_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row4.addWidget(self.retention_slider)
        self.retention_label = self._make_label(f"{Defaults.RETENTION_MINUTES} min", 11)
        self.retention_label.setFixedWidth(65)
        self.retention_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.retention_slider.valueChanged.connect(lambda v: self.retention_label.setText(f"{v} min"))
        row4.addWidget(self.retention_label)
        layout.addLayout(row4)

        layout.addSpacing(8)

        # === Memory Settings ===
        layout.addWidget(self._make_label("Memory Settings", 12, bold=True))

        # Memory unit
        row5 = QHBoxLayout()
        row5.addWidget(self._make_label("Display unit:", 11, color="#aaaaaa"))
        row5.addStretch()
        self.unit_combo = self._make_combo(["KB", "MB", "GB"], Defaults.MEMORY_UNIT)
        row5.addWidget(self.unit_combo)
        layout.addLayout(row5)

        # System info
        cpu_threads = psutil.cpu_count() or 8
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))
        info_label = self._make_label(f"Detected: {cpu_threads} CPU threads, {ram_gb} GB RAM", 10, color="#666666")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        layout.addStretch()

        # Start Button
        self.start_btn = QPushButton("Start Monitoring")
        self.start_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.start_btn.setFixedHeight(44)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #ff6b6b;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn)

    def _update_mode_buttons(self):
        """Update mode button styles (both can be selected)."""
        active_style = """
            QPushButton {
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 6px;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: #3a3a4e;
                color: #888888;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #4a4a5e;
            }
        """
        self.cpu_btn.setStyleSheet(active_style if self.cpu_btn.isChecked() else inactive_style)
        self.mem_btn.setStyleSheet(active_style if self.mem_btn.isChecked() else inactive_style)

        # Disable start if nothing selected
        self.start_btn.setEnabled(self.cpu_btn.isChecked() or self.mem_btn.isChecked())

    def _on_start(self):
        """Handle start button click."""
        if not self.cpu_btn.isChecked() and not self.mem_btn.isChecked():
            return
        self.accept()

    def get_settings(self) -> InitialSettings:
        """Get settings from dialog."""
        return InitialSettings(
            cpu_enabled=self.cpu_btn.isChecked(),
            memory_enabled=self.mem_btn.isChecked(),
            current_rows=int(self.current_combo.currentText()),
            history_rows=int(self.history_combo.currentText()),
            refresh_rate_ms=self.refresh_slider.value() * 100,
            retention_minutes=self.retention_slider.value(),
            memory_unit=self.unit_combo.currentText(),
        )
```

**Step 3: Commit**

```bash
git add app/settings_dialog.py
git commit -m "feat: add InitialSettingsDialog with checkbox mode selection"
```

---

## Task 4: Create CPUSettingsDialog and MemorySettingsDialog

**Files:**
- Modify: `app/settings_dialog.py` (add after InitialSettingsDialog)

**Step 1: Add CPUSettings dataclass**

```python
@dataclass
class CPUSettings:
    """Settings for CPU window only."""
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
```

**Step 2: Add MemorySettings dataclass**

```python
@dataclass
class MemorySettings:
    """Settings for Memory window only."""
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    memory_unit: str = Defaults.MEMORY_UNIT
```

**Step 3: Add CPUSettingsDialog class**

```python
class CPUSettingsDialog(QDialog):
    """Settings dialog for CPU window (no mode selection, no memory unit)."""

    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[CPUSettings] = None):
        super().__init__(parent)
        self.settings = settings or CPUSettings()
        self.setWindowTitle("CPU Monitor - Settings")
        self.setFixedSize(400, 380)

        icon_path = get_base_path() / "assets" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#2a2a3e"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#3a3a4e"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#e94560"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._setup_ui()
        self._load_settings()

    def _make_label(self, text: str, size: int = 12, bold: bool = False, color: str = "#ffffff") -> QLabel:
        label = QLabel(text)
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        label.setFont(QFont("Segoe UI", size, weight))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        return label

    def _make_combo(self, items: list, default: str, width: int = 100) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentText(default)
        combo.setFont(QFont("Segoe UI", 11))
        combo.setFixedWidth(width)
        combo.setFixedHeight(32)
        combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a4e; color: #ffffff;
                border: 1px solid #4a4a5e; border-radius: 4px; padding: 4px 8px;
            }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox::down-arrow {
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #3a3a4e; color: #ffffff;
                selection-background-color: #e94560;
            }
        """)
        return combo

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        title = self._make_label("CPU Monitor Settings", 16, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(12)

        # Current processes
        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_combo = self._make_combo([str(i) for i in range(1, 16)], "7")
        row1.addWidget(self.current_combo)
        layout.addLayout(row1)

        # History records
        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_combo = self._make_combo([str(i) for i in range(1, 16)], "4")
        row2.addWidget(self.history_combo)
        layout.addLayout(row2)

        # Refresh rate
        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("Refresh rate:", 11, color="#aaaaaa"))
        row3.addStretch()
        self.refresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.refresh_slider.setRange(5, 50)
        self.refresh_slider.setValue(20)
        self.refresh_slider.setFixedWidth(140)
        self.refresh_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row3.addWidget(self.refresh_slider)
        self.refresh_label = self._make_label("2000 ms", 11)
        self.refresh_label.setFixedWidth(65)
        self.refresh_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.refresh_slider.valueChanged.connect(lambda v: self.refresh_label.setText(f"{v * 100} ms"))
        row3.addWidget(self.refresh_label)
        layout.addLayout(row3)

        # Retention
        row4 = QHBoxLayout()
        row4.addWidget(self._make_label("History retention:", 11, color="#aaaaaa"))
        row4.addStretch()
        self.retention_slider = QSlider(Qt.Orientation.Horizontal)
        self.retention_slider.setRange(10, 360)
        self.retention_slider.setValue(120)
        self.retention_slider.setFixedWidth(140)
        self.retention_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row4.addWidget(self.retention_slider)
        self.retention_label = self._make_label("120 min", 11)
        self.retention_label.setFixedWidth(65)
        self.retention_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.retention_slider.valueChanged.connect(lambda v: self.retention_label.setText(f"{v} min"))
        row4.addWidget(self.retention_label)
        layout.addLayout(row4)

        layout.addStretch()

        # Apply button
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.apply_btn.setFixedHeight(44)
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.setStyleSheet("""
            QPushButton { background-color: #e94560; color: white; border: none; border-radius: 8px; }
            QPushButton:hover { background-color: #ff6b6b; }
        """)
        self.apply_btn.clicked.connect(self.accept)
        layout.addWidget(self.apply_btn)

    def _load_settings(self):
        self.current_combo.setCurrentText(str(self.settings.current_rows))
        self.history_combo.setCurrentText(str(self.settings.history_rows))
        self.refresh_slider.setValue(self.settings.refresh_rate_ms // 100)
        self.retention_slider.setValue(self.settings.retention_minutes)

    def get_settings(self) -> CPUSettings:
        return CPUSettings(
            current_rows=int(self.current_combo.currentText()),
            history_rows=int(self.history_combo.currentText()),
            refresh_rate_ms=self.refresh_slider.value() * 100,
            retention_minutes=self.retention_slider.value(),
        )
```

**Step 4: Add MemorySettingsDialog class**

```python
class MemorySettingsDialog(QDialog):
    """Settings dialog for Memory window (no mode selection, has memory unit)."""

    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[MemorySettings] = None):
        super().__init__(parent)
        self.settings = settings or MemorySettings()
        self.setWindowTitle("Memory Monitor - Settings")
        self.setFixedSize(400, 440)

        icon_path = get_base_path() / "assets" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#2a2a3e"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#3a3a4e"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#e94560"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._setup_ui()
        self._load_settings()

    def _make_label(self, text: str, size: int = 12, bold: bool = False, color: str = "#ffffff") -> QLabel:
        label = QLabel(text)
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        label.setFont(QFont("Segoe UI", size, weight))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        return label

    def _make_combo(self, items: list, default: str, width: int = 100) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentText(default)
        combo.setFont(QFont("Segoe UI", 11))
        combo.setFixedWidth(width)
        combo.setFixedHeight(32)
        combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a4e; color: #ffffff;
                border: 1px solid #4a4a5e; border-radius: 4px; padding: 4px 8px;
            }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox::down-arrow {
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #3a3a4e; color: #ffffff;
                selection-background-color: #e94560;
            }
        """)
        return combo

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        title = self._make_label("Memory Monitor Settings", 16, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(12)

        # Current processes
        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_combo = self._make_combo([str(i) for i in range(1, 16)], "7")
        row1.addWidget(self.current_combo)
        layout.addLayout(row1)

        # History records
        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_combo = self._make_combo([str(i) for i in range(1, 16)], "4")
        row2.addWidget(self.history_combo)
        layout.addLayout(row2)

        # Refresh rate
        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("Refresh rate:", 11, color="#aaaaaa"))
        row3.addStretch()
        self.refresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.refresh_slider.setRange(5, 50)
        self.refresh_slider.setValue(20)
        self.refresh_slider.setFixedWidth(140)
        self.refresh_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row3.addWidget(self.refresh_slider)
        self.refresh_label = self._make_label("2000 ms", 11)
        self.refresh_label.setFixedWidth(65)
        self.refresh_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.refresh_slider.valueChanged.connect(lambda v: self.refresh_label.setText(f"{v * 100} ms"))
        row3.addWidget(self.refresh_label)
        layout.addLayout(row3)

        # Retention
        row4 = QHBoxLayout()
        row4.addWidget(self._make_label("History retention:", 11, color="#aaaaaa"))
        row4.addStretch()
        self.retention_slider = QSlider(Qt.Orientation.Horizontal)
        self.retention_slider.setRange(10, 360)
        self.retention_slider.setValue(120)
        self.retention_slider.setFixedWidth(140)
        self.retention_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row4.addWidget(self.retention_slider)
        self.retention_label = self._make_label("120 min", 11)
        self.retention_label.setFixedWidth(65)
        self.retention_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.retention_slider.valueChanged.connect(lambda v: self.retention_label.setText(f"{v} min"))
        row4.addWidget(self.retention_label)
        layout.addLayout(row4)

        layout.addSpacing(8)

        # Memory unit
        layout.addWidget(self._make_label("Memory Settings", 12, bold=True))
        row5 = QHBoxLayout()
        row5.addWidget(self._make_label("Display unit:", 11, color="#aaaaaa"))
        row5.addStretch()
        self.unit_combo = self._make_combo(["KB", "MB", "GB"], "MB")
        row5.addWidget(self.unit_combo)
        layout.addLayout(row5)

        layout.addStretch()

        # Apply button
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.apply_btn.setFixedHeight(44)
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.setStyleSheet("""
            QPushButton { background-color: #e94560; color: white; border: none; border-radius: 8px; }
            QPushButton:hover { background-color: #ff6b6b; }
        """)
        self.apply_btn.clicked.connect(self.accept)
        layout.addWidget(self.apply_btn)

    def _load_settings(self):
        self.current_combo.setCurrentText(str(self.settings.current_rows))
        self.history_combo.setCurrentText(str(self.settings.history_rows))
        self.refresh_slider.setValue(self.settings.refresh_rate_ms // 100)
        self.retention_slider.setValue(self.settings.retention_minutes)
        self.unit_combo.setCurrentText(self.settings.memory_unit)

    def get_settings(self) -> MemorySettings:
        return MemorySettings(
            current_rows=int(self.current_combo.currentText()),
            history_rows=int(self.history_combo.currentText()),
            refresh_rate_ms=self.refresh_slider.value() * 100,
            retention_minutes=self.retention_slider.value(),
            memory_unit=self.unit_combo.currentText(),
        )
```

**Step 5: Commit**

```bash
git add app/settings_dialog.py
git commit -m "feat: add CPUSettingsDialog and MemorySettingsDialog"
```

---

## Task 5: Create CPUWindow and MemoryWindow Classes

**Files:**
- Modify: `app/main_window.py`

**Step 1: Refactor MainWindow into BaseMonitorWindow**

Rename `MainWindow` to `BaseMonitorWindow` and make it a base class that handles common functionality. Then create `CPUWindow` and `MemoryWindow` subclasses.

See implementation in Task 5 code block below.

**Step 2: Add to main_window.py imports**

```python
from .settings_dialog import (
    MonitorSettings,
    SettingsDialog,
    InitialSettings,
    CPUSettings,
    MemorySettings,
    CPUSettingsDialog,
    MemorySettingsDialog,
)
from .monitor import MonitorMode, MonitorWorker, MonitorData, SharedDataCollector
```

**Step 3: Refactor MainWindow into BaseMonitorWindow**

The BaseMonitorWindow contains all common code. CPUWindow and MemoryWindow override:
- `_get_mode()` - returns MonitorMode
- `_get_title()` - returns window title
- `_show_settings()` - shows appropriate settings dialog
- `_get_mode_cols()` - returns "cpu" or "none" for table columns

```python
class BaseMonitorWindow(QMainWindow):
    """Base class for monitor windows."""

    # ... (existing MainWindow code, but without settings dialog call in __init__)

    def _get_mode(self) -> MonitorMode:
        """Override in subclass."""
        raise NotImplementedError

    def _get_title(self) -> str:
        """Override in subclass."""
        raise NotImplementedError

    def _get_mode_cols(self) -> str:
        """Override in subclass. Returns 'cpu' or 'none'."""
        raise NotImplementedError


class CPUWindow(BaseMonitorWindow):
    """CPU Monitor window."""

    def __init__(self, initial_settings: InitialSettings, collector: SharedDataCollector):
        self._initial_settings = initial_settings
        self._collector = collector
        self._cpu_settings = CPUSettings(
            current_rows=initial_settings.current_rows,
            history_rows=initial_settings.history_rows,
            refresh_rate_ms=initial_settings.refresh_rate_ms,
            retention_minutes=initial_settings.retention_minutes,
        )
        super().__init__()

        # Connect to shared collector
        self._collector.cpu_data_ready.connect(self._on_data_ready)

    def _get_mode(self) -> MonitorMode:
        return MonitorMode.CPU

    def _get_title(self) -> str:
        return "CPU Monitor"

    def _get_mode_cols(self) -> str:
        return "cpu"

    def _show_settings(self):
        """Show CPU settings dialog."""
        dialog = CPUSettingsDialog(self, self._cpu_settings)
        if dialog.exec():
            self._cpu_settings = dialog.get_settings()
            self._apply_cpu_settings()

    def _apply_cpu_settings(self):
        """Apply CPU settings."""
        self._collector.configure_cpu(
            cpu_threads=self._initial_settings.cpu_threads,
            ram_gb=self._initial_settings.ram_gb,
            current_rows=self._cpu_settings.current_rows,
            history_rows=self._cpu_settings.history_rows,
            retention_minutes=self._cpu_settings.retention_minutes,
            refresh_rate_ms=self._cpu_settings.refresh_rate_ms,
        )
        self._rebuild_tables()

    def closeEvent(self, event):
        """Handle close - disable CPU in collector."""
        self._collector.disable_cpu()
        super().closeEvent(event)


class MemoryWindow(BaseMonitorWindow):
    """Memory Monitor window."""

    def __init__(self, initial_settings: InitialSettings, collector: SharedDataCollector):
        self._initial_settings = initial_settings
        self._collector = collector
        self._memory_settings = MemorySettings(
            current_rows=initial_settings.current_rows,
            history_rows=initial_settings.history_rows,
            refresh_rate_ms=initial_settings.refresh_rate_ms,
            retention_minutes=initial_settings.retention_minutes,
            memory_unit=initial_settings.memory_unit,
        )
        super().__init__()

        # Connect to shared collector
        self._collector.memory_data_ready.connect(self._on_data_ready)

    def _get_mode(self) -> MonitorMode:
        return MonitorMode.MEMORY

    def _get_title(self) -> str:
        return "Memory Monitor"

    def _get_mode_cols(self) -> str:
        return "none"

    def _show_settings(self):
        """Show Memory settings dialog."""
        dialog = MemorySettingsDialog(self, self._memory_settings)
        if dialog.exec():
            self._memory_settings = dialog.get_settings()
            self._apply_memory_settings()

    def _apply_memory_settings(self):
        """Apply Memory settings."""
        self._collector.configure_memory(
            cpu_threads=self._initial_settings.cpu_threads,
            ram_gb=self._initial_settings.ram_gb,
            current_rows=self._memory_settings.current_rows,
            history_rows=self._memory_settings.history_rows,
            retention_minutes=self._memory_settings.retention_minutes,
            refresh_rate_ms=self._memory_settings.refresh_rate_ms,
            memory_unit=self._memory_settings.memory_unit,
        )
        self._rebuild_tables()

    def closeEvent(self, event):
        """Handle close - disable Memory in collector."""
        self._collector.disable_memory()
        super().closeEvent(event)
```

**Step 4: Commit**

```bash
git add app/main_window.py
git commit -m "feat: refactor MainWindow into BaseMonitorWindow with CPU/Memory subclasses"
```

---

## Task 6: Update main.py Entry Point

**Files:**
- Modify: `main.py`

**Step 1: Update imports and main function**

```python
#!/usr/bin/env python3
"""
Process Monitor - Entry Point

Real-time CPU and Memory usage monitoring for Windows processes.
"""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import CPUWindow, MemoryWindow
from app.monitor import SharedDataCollector
from app.settings_dialog import InitialSettingsDialog


def get_base_path() -> Path:
    """Get base path for resources (handles PyInstaller frozen exe)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def main():
    """Application entry point."""
    # Set Windows taskbar icon (must be before QApplication)
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PCGadgets.PMUsage")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Process Monitor")
    app.setApplicationVersion("2.1.0")
    app.setOrganizationName("PC Gadgets")

    # Set app icon
    base = get_base_path()
    icon_path = base / "assets" / "icon.ico"
    if not icon_path.exists():
        icon_path = base / "assets" / "icon.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Show initial settings dialog
    dialog = InitialSettingsDialog()
    if not dialog.exec():
        return 0

    settings = dialog.get_settings()

    # Create shared data collector
    collector = SharedDataCollector()

    # Track windows for cleanup
    windows = []

    # Create CPU window if enabled
    if settings.cpu_enabled:
        cpu_window = CPUWindow(settings, collector)
        collector.configure_cpu(
            cpu_threads=settings.cpu_threads,
            ram_gb=settings.ram_gb,
            current_rows=settings.current_rows,
            history_rows=settings.history_rows,
            retention_minutes=settings.retention_minutes,
            refresh_rate_ms=settings.refresh_rate_ms,
        )
        cpu_window.show()
        windows.append(cpu_window)

    # Create Memory window if enabled
    if settings.memory_enabled:
        memory_window = MemoryWindow(settings, collector)
        collector.configure_memory(
            cpu_threads=settings.cpu_threads,
            ram_gb=settings.ram_gb,
            current_rows=settings.current_rows,
            history_rows=settings.history_rows,
            retention_minutes=settings.retention_minutes,
            refresh_rate_ms=settings.refresh_rate_ms,
            memory_unit=settings.memory_unit,
        )
        memory_window.show()
        # Offset second window
        if len(windows) > 0:
            memory_window.move(
                windows[0].x() + windows[0].width() + 20,
                windows[0].y()
            )
        windows.append(memory_window)

    # Start collector
    collector.start()

    # Run event loop
    result = app.exec()

    # Cleanup
    collector.stop()
    SharedDataCollector.reset_instance()

    return result


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Commit**

```bash
git add main.py
git commit -m "feat: update main.py to use InitialSettingsDialog and dual windows"
```

---

## Task 7: Update __init__.py Exports

**Files:**
- Modify: `app/__init__.py`

**Step 1: Update exports**

```python
"""Process Monitor Application."""

from .main_window import CPUWindow, MemoryWindow, BaseMonitorWindow
from .monitor import MonitorMode, ProcessMonitor, SharedDataCollector
from .settings_dialog import (
    InitialSettingsDialog,
    CPUSettingsDialog,
    MemorySettingsDialog,
    InitialSettings,
    CPUSettings,
    MemorySettings,
)

__all__ = [
    "CPUWindow",
    "MemoryWindow",
    "BaseMonitorWindow",
    "MonitorMode",
    "ProcessMonitor",
    "SharedDataCollector",
    "InitialSettingsDialog",
    "CPUSettingsDialog",
    "MemorySettingsDialog",
    "InitialSettings",
    "CPUSettings",
    "MemorySettings",
]
```

**Step 2: Commit**

```bash
git add app/__init__.py
git commit -m "feat: update exports for new window classes"
```

---

## Task 8: Update README.md Documentation

**Files:**
- Modify: `README.md`

**Step 1: Update documentation with new architecture**

Update the Architecture section with new mermaid diagram and update features/usage sections.

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with dual monitor architecture"
```

---

## Task 9: Manual Testing

**Steps:**
1. Run `python main.py`
2. Test: Select only CPU → one window opens
3. Test: Select only Memory → one window opens
4. Test: Select both → two windows open side by side
5. Test: Each window's Settings button opens correct dialog
6. Test: Close one window → other continues working
7. Test: Pause/Resume works independently per window

---

## Summary

| Task | Description |
|------|-------------|
| 1 | Add MonitorMode.BOTH enum |
| 2 | Create SharedDataCollector singleton |
| 3 | Create InitialSettingsDialog with checkboxes |
| 4 | Create CPUSettingsDialog and MemorySettingsDialog |
| 5 | Refactor MainWindow into Base/CPU/Memory windows |
| 6 | Update main.py entry point |
| 7 | Update __init__.py exports |
| 8 | Update README.md documentation |
| 9 | Manual testing |

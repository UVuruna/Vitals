"""The right-click process menu and the actions it offers.

Right-clicking any row in any of the three tables opens a menu that is half
INFORMATION (the signing company, every PID, the exe path — each line clickable
to copy) and half ACTIONS (kill, open file location, set priority).

Everything here works on LIVE processes looked up by display name at the
moment of the click, never on the row's rendered numbers: the table shows an
aggregate that may be seconds old, and killing something on stale identity is
exactly the mistake to avoid.
"""

from pathlib import Path
from textwrap import wrap

from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QTableWidget

from .. import icons
from ..color_management import ProcessColorManager
from ..dialogs.process_dialog import KillConfirmDialog, PriorityDialog
from ..process_actions import (
    find_processes,
    get_current_priority,
    get_exe_path,
    kill_processes,
    open_file_location,
    set_priority,
)
from ..styles import Dimensions, context_menu_style


# ═════════════════════════════ THE MENU ═════════════════════════════

def show_process_menu(window, pos, table: QTableWidget, has_total_row: bool = False) -> None:
    """Show the process action menu for the row under `pos`."""
    index = table.indexAt(pos)
    if not index.isValid():
        return
    row = index.row()
    # Block Σ total row (always the last row in current processes table)
    if has_total_row and row == table.rowCount() - 1:
        return
    name_item = table.item(row, 1)
    if not name_item or not name_item.text():
        return

    process_name = name_item.text()

    # Gather live process info for the info section
    procs = find_processes(process_name)
    pids = [p.pid for p in procs]
    exe_path = get_exe_path(procs) if procs else None

    # Full PID string for clipboard copy
    pid_clipboard = ", ".join(str(p) for p in pids)

    palette = window._theme.palette
    menu = QMenu(window)
    menu.setStyleSheet(context_menu_style(palette))

    # Info section — the company that signed the exe leads it, wrapped
    # across as many lines as the name needs (owner 2026-07-24), with the
    # row's own color as a swatch so the menu ties back to the table.
    color_mgr = ProcessColorManager()
    company = color_mgr.get_company_name(process_name)
    company_actions: list = []
    if company:
        proc_color = color_mgr.get_process_color(process_name, palette)
        for i, line in enumerate(wrap(company, Dimensions.MENU_LINE_CHARS)):
            act = menu.addAction(line)
            if i == 0 and proc_color:
                act.setIcon(icons.swatch(proc_color))
            act.setToolTip("Click to copy the company name to clipboard")
            company_actions.append(act)
        menu.addSeparator()

    # PIDs split 10 per row, click any line to copy all
    pid_actions: list = []
    if pids:
        label = "PIDs" if len(pids) > 1 else "PID"
        chunks = [pids[i:i + 10] for i in range(0, len(pids), 10)]
        for i, chunk in enumerate(chunks):
            chunk_str = ", ".join(str(p) for p in chunk)
            prefix = f"{label}: " if i == 0 else "  "
            act = menu.addAction(f"{prefix}{chunk_str}")
            act.setToolTip("Click to copy all PIDs to clipboard")
            pid_actions.append(act)

    exe_action = None
    if exe_path:
        exe_action = menu.addAction(f"EXE: {Path(exe_path).name}")
        exe_action.setToolTip(f"{exe_path}\nClick to copy to clipboard")

    if pid_actions or exe_action:
        menu.addSeparator()

    kill_action = menu.addAction("Kill Process...")
    menu.addSeparator()
    open_action = menu.addAction("Open File Location")
    menu.addSeparator()
    priority_action = menu.addAction("Set Priority...")

    action = menu.exec(table.viewport().mapToGlobal(pos))

    if action is None:
        return
    if action in company_actions:
        QApplication.clipboard().setText(company)
    elif action in pid_actions:
        QApplication.clipboard().setText(pid_clipboard)
    elif action == exe_action:
        QApplication.clipboard().setText(exe_path)
    elif action == kill_action:
        do_kill(window, process_name)
    elif action == open_action:
        do_open_location(window, process_name)
    elif action == priority_action:
        do_set_priority(window, process_name)


# ═════════════════════════════ THE ACTIONS ═════════════════════════════

def do_kill(window, process_name: str) -> None:
    """Kill all instances of the process after confirmation."""
    procs = find_processes(process_name)
    if not procs:
        QMessageBox.information(window, "Kill Process", f"No running instances of '{process_name}' found.")
        return
    palette = window._theme.palette
    proc_color = ProcessColorManager().get_process_color(process_name, palette)
    dialog = KillConfirmDialog(window, process_name, len(procs), palette, proc_color)
    if dialog.exec():
        killed, errors = kill_processes(procs)
        if errors:
            QMessageBox.warning(
                window, "Kill Process",
                f"Killed {killed} instance(s).\n\nErrors:\n" + "\n".join(errors),
            )


def do_open_location(window, process_name: str) -> None:
    """Open Explorer with the process exe file selected."""
    procs = find_processes(process_name)
    if not procs:
        QMessageBox.information(window, "Open File Location", f"No running instances of '{process_name}' found.")
        return
    path = get_exe_path(procs)
    if not path:
        QMessageBox.warning(window, "Open File Location", "Could not get file path. Access denied.")
        return
    open_file_location(path)


def do_set_priority(window, process_name: str) -> None:
    """Set Windows priority class for all instances of the process."""
    procs = find_processes(process_name)
    if not procs:
        QMessageBox.information(window, "Set Priority", f"No running instances of '{process_name}' found.")
        return
    palette = window._theme.palette
    proc_color = ProcessColorManager().get_process_color(process_name, palette)
    current_prio = get_current_priority(procs)
    dialog = PriorityDialog(window, process_name, current_prio, palette, proc_color)
    if dialog.exec():
        new_prio = dialog.get_selected_priority()
        if new_prio is not None:
            changed, errors = set_priority(procs, new_prio)
            if errors:
                QMessageBox.warning(
                    window, "Set Priority",
                    f"Updated {changed} instance(s).\n\nErrors:\n" + "\n".join(errors),
                )

"""Windows shell integration for the gadget windows.

Two things Vitals needs from the shell that Qt does not offer:

- **A per-window taskbar identity.** When several windows share one
  process-level AppUserModelID, Windows shows the exe's group icon instead of
  each window's own. Setting `PKEY_AppUserModel_ID` and
  `PKEY_AppUserModel_RelaunchIconResource` per window through IPropertyStore
  tells the shell exactly which icon to use.
- **An elevated relaunch.** The ETW kernel trace cannot be started from a
  medium-integrity process, so no in-process retry can ever fix NEEDS_ADMIN —
  only a new elevated process can.

Both are `ctypes` calls into shell32/user32. Icon cosmetics are best-effort by
design: a failure is reported to stderr and swallowed, never allowed to take
the window down with it.
"""

import ctypes
import sys
from ctypes import (
    HRESULT,
    POINTER,
    Structure,
    WINFUNCTYPE,
    byref,
    c_byte,
    c_ulong,
    c_ushort,
    c_void_p,
    c_wchar_p,
)
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget


# ═══════════════════════════ ELEVATED RELAUNCH ═══════════════════════════

def relaunch_elevated() -> None:
    """Restart Vitals with Administrator rights, then quit this instance.

    The ETW kernel trace cannot be started from a medium-integrity process, so
    an in-process retry can never fix NEEDS_ADMIN — only a new elevated
    process can. A refused UAC prompt leaves the current instance running and
    is reported, never swallowed (root Rule #1).
    """
    if getattr(sys, 'frozen', False):
        target, params = sys.executable, ""
    else:
        target = sys.executable
        params = f'"{Path(__file__).parent.parent.parent / "main.py"}"'

    # >32 means the shell accepted it; anything else (including 5, the user
    # declining the prompt) means we are staying where we are.
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", target, params, None, 1)
    if result > 32:
        QApplication.instance().quit()
    else:
        print(f"[Vitals] Elevated relaunch declined or failed (code {result})", file=sys.stderr)


# ══════════════════════════ PER-WINDOW TASKBAR ICON ══════════════════════════

def set_native_taskbar_icon(window: QWidget, ico_path: Path | None) -> None:
    """Set a per-window icon via COM IPropertyStore + WM_SETICON.

    When multiple windows share a process-level AppUserModelID, Windows
    uses the group icon (from the exe) instead of per-window icons.
    Setting PKEY_AppUserModel_ID and PKEY_AppUserModel_RelaunchIconResource
    per-window via IPropertyStore tells the shell exactly which icon to use.

    Intentional best-effort: icon cosmetics must never crash the app, so any
    failure here is reported to stderr and swallowed. This runs once per
    window (guarded by _native_icon_set in showEvent), so a plain print is
    enough — it can never spam the log.
    """
    try:
        if not ico_path or not ico_path.exists():
            return

        hwnd = int(window.winId())
        ico_abs = str(ico_path.resolve())

        # --- COM structures for IPropertyStore ---
        class GUID(Structure):
            _fields_ = [
                ('Data1', c_ulong), ('Data2', c_ushort),
                ('Data3', c_ushort), ('Data4', c_byte * 8),
            ]

        class PROPERTYKEY(Structure):
            _fields_ = [('fmtid', GUID), ('pid', c_ulong)]

        class PROPVARIANT(Structure):
            _fields_ = [
                ('vt', c_ushort), ('r1', c_ushort),
                ('r2', c_ushort), ('r3', c_ushort),
                ('ptr', c_void_p), ('_pad', c_void_p),
            ]

        VT_LPWSTR = 31

        IID_IPropertyStore = GUID(
            0x886D8EEB, 0x8CF2, 0x4446,
            (c_byte * 8)(0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99),
        )
        APPMODEL_FMTID = GUID(
            0x9F4C2855, 0x9F79, 0x4B39,
            (c_byte * 8)(0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3),
        )
        PK_ID = PROPERTYKEY(APPMODEL_FMTID, 5)    # AppUserModel_ID
        PK_ICON = PROPERTYKEY(APPMODEL_FMTID, 3)  # RelaunchIconResource

        pps = c_void_p()
        hr = ctypes.windll.shell32.SHGetPropertyStoreForWindow(
            hwnd, byref(IID_IPropertyStore), byref(pps),
        )
        if hr == 0 and pps:
            try:
                vt_ptr = ctypes.cast(pps, POINTER(c_void_p))[0]
                vt = ctypes.cast(vt_ptr, POINTER(c_void_p * 8)).contents
                SET_FN = WINFUNCTYPE(
                    HRESULT, c_void_p,
                    POINTER(PROPERTYKEY), POINTER(PROPVARIANT),
                )
                SetValue = SET_FN(vt[6])

                def _set_prop(key, text):
                    pv = PROPVARIANT()
                    pv.vt = VT_LPWSTR
                    buf = c_wchar_p(text)
                    pv.ptr = ctypes.cast(buf, c_void_p)
                    SetValue(pps, byref(key), byref(pv))

                _set_prop(PK_ID, "PCGadgets.Vitals")

                # Icon resource: exe when frozen, ico file from source
                if getattr(sys, 'frozen', False):
                    _set_prop(PK_ICON, f"{sys.executable},0")
                else:
                    _set_prop(PK_ICON, f"{ico_abs},0")
            finally:
                REL_FN = WINFUNCTYPE(c_ulong, c_void_p)
                REL_FN(vt[2])(pps)

        # --- WM_SETICON fallback ---
        if ico_abs.endswith('.ico'):
            LR_LOADFROMFILE = 0x00000010
            hbig = ctypes.windll.user32.LoadImageW(
                None, ico_abs, 1, 32, 32, LR_LOADFROMFILE,
            )
            hsmall = ctypes.windll.user32.LoadImageW(
                None, ico_abs, 1, 16, 16, LR_LOADFROMFILE,
            )
            if hbig:
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hbig)
            if hsmall:
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hsmall)
    except Exception as e:
        print(f"[Vitals] set_native_taskbar_icon failed (cosmetic): {e}", file=sys.stderr)

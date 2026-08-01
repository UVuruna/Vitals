"""THE STRUCTURE LAW guard — no god-files.

Fails the build when any source file crosses the ~1,000-line Violation
threshold and is not named in RATCHET below.

The RATCHET may only SHRINK. Adding an entry requires the owner's explicit
approval in that same session; an autonomous run that cannot safely fix a
violation may add one marked `pending owner ratification` and MUST surface it
at the top of its final report.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# A file above this many lines holds more than one responsibility until proven
# otherwise (root rules/CODE.md — THE STRUCTURE LAW).
VIOLATION_LINES = 1000

# Directories that hold no hand-written source of ours.
EXCLUDED_DIRS = {
    "build", "dist", "exe", "__pycache__", ".git", ".claude",
    "venv", ".venv", "node_modules", "UV",
}

# ---------------------------------------------------------------------------
# RATCHET — files allowed to stay over the threshold.
#
# Format: "relative/path.py": "why it stays whole + who owes the split"
#
# EMPTY IS THE GOAL. The 2026-08-02 split session cleared every entry it
# would otherwise have had to add:
#   app/main_window.py     2,085 -> split into app/windows/ (8 modules)
#   app/settings_dialog.py 1,634 -> split into app/dialogs/ (7 modules)
#   app/monitor.py         1,477 -> split into app/collect/ (8 modules)
# ---------------------------------------------------------------------------
RATCHET: dict[str, str] = {}


def source_files() -> list[Path]:
    """Every hand-written Python source file in the project."""
    return sorted(
        path
        for path in PROJECT_ROOT.rglob("*.py")
        if not (set(path.relative_to(PROJECT_ROOT).parts) & EXCLUDED_DIRS)
    )


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_no_god_files():
    """No source file exceeds the Violation threshold outside the ratchet."""
    violations = []
    for path in source_files():
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if rel in RATCHET:
            continue
        lines = line_count(path)
        if lines > VIOLATION_LINES:
            violations.append(f"{rel}: {lines} lines (limit {VIOLATION_LINES})")

    assert not violations, (
        "THE STRUCTURE LAW — split these by responsibility, or add a ratchet "
        "entry with the owner's explicit approval:\n  "
        + "\n  ".join(violations)
    )


def test_ratchet_entries_are_real():
    """Every ratchet entry names a file that exists and is actually over."""
    stale = []
    for rel, reason in RATCHET.items():
        path = PROJECT_ROOT / rel
        if not path.exists():
            stale.append(f"{rel}: ratcheted but the file no longer exists")
        elif line_count(path) <= VIOLATION_LINES:
            stale.append(
                f"{rel}: now {line_count(path)} lines — the ratchet entry is "
                "paid off and must be deleted"
            )
        elif not reason.strip():
            stale.append(f"{rel}: ratchet entry has no reason")

    assert not stale, (
        "The ratchet may only shrink — remove paid-off entries:\n  "
        + "\n  ".join(stale)
    )


@pytest.mark.parametrize("path", source_files(), ids=lambda p: p.name)
def test_file_is_readable(path: Path):
    """Every source file parses as text (guards against a broken scan)."""
    assert line_count(path) >= 0

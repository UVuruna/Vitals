"""THE CONFIG SECTION LAW guard.

A config/data file is a STRUCTURE, not a notebook. For every file named in
CONFIG_FILES this guard fails the build on:

1. a top-level definition that sits before the file's first section banner
   (module docstring, `__future__`, imports and `if TYPE_CHECKING:` exempt);
2. a duplicate key inside any dict literal;
3. post-definition patching of an earlier module-level table
   (`TABLE[...] = ...` or `TABLE.update(...)` at module level).

A section banner is ONE comment line carrying the section name between two
runs of at least 8 rule characters:

    # ═══════════════════════════ SECTION NAME ═══════════════════════════

Scope note: this guard reads MODULE-LEVEL statements only. A config-like table
hidden inside a class body is invisible to it — that is itself a placement
smell to fix by lifting the table to module level, never a reason to widen
this list.
"""

import ast
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# CONFIG_FILES — seeded narrowly (root rules/CODE.md): genuinely
# config-centric modules only. A file that is mostly algorithm with one small
# table stays OUT.
#
#   app/styles.py — the non-color config home: dimensions, switch geometry,
#                   fonts, defaults, unit tables, process aliases.
#   app/theme.py  — the COLOR config home: the DARK and LIGHT palettes are
#                   the single source of truth for every color in the app,
#                   and "add one color" must edit the palette in place.
#
# Deliberately OUT: app/color_management.py (mostly ranking/shading algorithm
# around small default tables) and config/config.json (JSON — this guard is
# Python-AST based). See OPEN-QUESTIONS.md.
# ---------------------------------------------------------------------------
CONFIG_FILES = [
    "app/styles.py",
    "app/theme.py",
]

# One comment line: rule run, section name, rule run.
BANNER = re.compile(r"^\s*#\s*[=═─━_-]{8,}\s*(\S.*?)\s*[=═─━_-]{8,}\s*$")

# Statements allowed above the first banner.
_PREAMBLE = (ast.Import, ast.ImportFrom)


def banner_lines(text: str) -> list[int]:
    """1-based line numbers of every section banner in the file."""
    return [i for i, line in enumerate(text.splitlines(), 1) if BANNER.match(line)]


def config_paths() -> list[Path]:
    return [PROJECT_ROOT / rel for rel in CONFIG_FILES]


@pytest.mark.parametrize("rel", CONFIG_FILES)
def test_config_file_exists(rel: str):
    assert (PROJECT_ROOT / rel).exists(), f"CONFIG_FILES names a missing file: {rel}"


@pytest.mark.parametrize("rel", CONFIG_FILES)
def test_has_section_banners(rel: str):
    text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
    assert banner_lines(text), (
        f"{rel}: no section banner found. Organize the file under banners:\n"
        "    # ═══════════════════════════ SECTION NAME ═══════════════════════════"
    )


@pytest.mark.parametrize("rel", CONFIG_FILES)
def test_every_definition_lives_under_a_banner(rel: str):
    """No top-level definition may precede the first section banner."""
    path = PROJECT_ROOT / rel
    text = path.read_text(encoding="utf-8")
    first_banner = min(banner_lines(text), default=None)
    assert first_banner is not None, f"{rel}: no section banner (see previous test)"

    tree = ast.parse(text, filename=str(path))
    orphans = []
    for node in tree.body:
        if isinstance(node, _PREAMBLE):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # module docstring / stray string
        if node.lineno < first_banner:
            orphans.append(f"line {node.lineno}: {type(node).__name__}")

    assert not orphans, (
        f"{rel}: top-level definitions sit above the first section banner "
        f"(line {first_banner}) — every definition belongs to a named "
        f"section:\n  " + "\n  ".join(orphans)
    )


@pytest.mark.parametrize("rel", CONFIG_FILES)
def test_no_duplicate_dict_keys(rel: str):
    """A repeated literal key silently discards the earlier entry."""
    path = PROJECT_ROOT / rel
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    duplicates = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        seen: set = set()
        for key in node.keys:
            if not isinstance(key, ast.Constant):
                continue
            marker = (type(key.value).__name__, key.value)
            if marker in seen:
                duplicates.append(f"line {key.lineno}: duplicate key {key.value!r}")
            seen.add(marker)

    assert not duplicates, f"{rel}: duplicate dict keys:\n  " + "\n  ".join(duplicates)


@pytest.mark.parametrize("rel", CONFIG_FILES)
def test_no_post_definition_patching(rel: str):
    """A table is defined ONCE, whole, in its section — never patched later."""
    path = PROJECT_ROOT / rel
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    defined: set[str] = set()
    patches = []

    for node in tree.body:
        # X = ... / X: T = ...  → remember the module-level name
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]

        for target in targets:
            if isinstance(target, ast.Name):
                defined.add(target.id)
            elif isinstance(target, ast.Subscript):
                root = target
                while isinstance(root, ast.Subscript):
                    root = root.value
                if isinstance(root, ast.Name) and root.id in defined:
                    patches.append(
                        f"line {node.lineno}: {root.id}[...] = ... patches a table "
                        "defined earlier — edit the structure in place instead"
                    )

        # X.update(...) at module level
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in {"update", "setdefault", "append", "extend"}
                and isinstance(func.value, ast.Name)
                and func.value.id in defined
            ):
                patches.append(
                    f"line {node.lineno}: {func.value.id}.{func.attr}(...) patches a "
                    "table defined earlier — edit the structure in place instead"
                )

    assert not patches, (
        f"{rel}: post-definition patching is forbidden:\n  " + "\n  ".join(patches)
    )

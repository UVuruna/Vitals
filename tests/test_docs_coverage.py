"""THE DOCS LAW guard, part 2 — coverage by tier.

Every source file must carry the docs its TIER requires, and no more:

| Tier | Obligation |
|------|------------|
| Trivial | one line in the folder doc — NO own docs (an extra doc FAILS) |
| Standard | `__about/{name}.md` |
| Algorithmic | `__about/{name}.md` **and** `__flow/{name}.md` |
| tests | the folder doc `___tests.md` only |

The tier lists below ARE the tier assignment. Changing a file's tier means
editing this test in the same commit — that is the point: a tier is a decision,
not a coincidence.

A flow doc must EARN its place (owner decision 2026-08-01). Being a widget, a
config table or a protocol does not make a file Algorithmic. The test: *would
the diagram just restate the code?* Then it is Standard. `FLOW_REQUIRED` is
therefore deliberately short — 13 of 46 source files.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXCLUDED_DIRS = {
    "build", "dist", "exe", "__pycache__", ".git", ".claude",
    "venv", ".venv", "node_modules", "UV", ".pytest_cache",
}

# ---------------------------------------------------------------------------
# TRIVIAL — glue and re-exports. One line in the folder doc, no own docs.
# ---------------------------------------------------------------------------
TRIVIAL = {
    "app/__init__.py",
    "app/collect/__init__.py",
    "app/dialogs/__init__.py",
    "app/windows/__init__.py",
}

# ---------------------------------------------------------------------------
# ALGORITHMIC — a diagram genuinely tells the story better than the code.
# Real multi-step algorithms, one nontrivial GUI layout, and the two config
# files whose structure needs a picture. Everything else is Standard.
# ---------------------------------------------------------------------------
FLOW_REQUIRED = {
    "main.py",                          # startup sequence
    "app/theme.py",                     # palette tree + scope model
    "app/styles.py",                    # config section tree
    "app/color_management.py",          # ranking + wheel + shading pipelines
    "app/transition.py",                # the cover/flip/fade sequence
    "app/collect/system_query.py",      # NtQSI buffer walk + CPU delta
    "app/collect/rolling_window.py",    # accumulator + bucketed expiry
    "app/collect/process_stats.py",     # one tick: top-N, peaks, history, rolling
    "app/collect/network_trace.py",     # ETW session lifecycle + failure states
    "app/collect/collector.py",         # the tick loop
    "app/dialogs/setup_dialog.py",      # the setup screen's layout
    "app/windows/base_window.py",       # window layout sketch + flip/tick paths
    "app/windows/placement.py",         # the frame-vs-client clamp
}

# ---------------------------------------------------------------------------
# Test modules document as a folder, never per file.
# ---------------------------------------------------------------------------
TESTS_DIR = "tests"

# Folders whose source files are documented, and the folder doc each must have.
# The project ROOT is absent on purpose: main.py sits directly in it, so under
# the flat-root rule README.md plays the folder-doc role and `__about/` /
# `__flow/` sit directly under the root.
FOLDER_DOCS = {
    "app": "app/___app.md",
    "app/collect": "app/collect/___collect.md",
    "app/dialogs": "app/dialogs/___dialogs.md",
    "app/windows": "app/windows/___windows.md",
    "setup": "setup/___setup.md",
    "tests": "tests/___tests.md",
}


def source_files() -> list[str]:
    """Every hand-written Python source file, as posix paths from the root."""
    return sorted(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in PROJECT_ROOT.rglob("*.py")
        if not (set(path.relative_to(PROJECT_ROOT).parts) & EXCLUDED_DIRS)
    )


def documented_files() -> list[str]:
    """Source files that owe at least an `__about/` doc."""
    return [
        rel for rel in source_files()
        if rel not in TRIVIAL and not rel.startswith(f"{TESTS_DIR}/")
    ]


def about_path(rel: str) -> Path:
    source = PROJECT_ROOT / rel
    return source.parent / "__about" / f"{source.stem}.md"


def flow_path(rel: str) -> Path:
    source = PROJECT_ROOT / rel
    return source.parent / "__flow" / f"{source.stem}.md"


# ═══════════════════════════ TIER LIST INTEGRITY ═══════════════════════════

@pytest.mark.parametrize("rel", sorted(TRIVIAL | FLOW_REQUIRED))
def test_tier_lists_name_real_files(rel: str):
    """A tier list may not name a file that no longer exists."""
    assert (PROJECT_ROOT / rel).exists(), (
        f"{rel} is in a tier list but does not exist — update this test in the "
        "same commit as the file's removal"
    )


def test_trivial_and_flow_lists_are_disjoint():
    overlap = TRIVIAL & FLOW_REQUIRED
    assert not overlap, f"a file cannot be both Trivial and Algorithmic: {overlap}"


# ═══════════════════════════════ COVERAGE ═══════════════════════════════

@pytest.mark.parametrize("rel", documented_files())
def test_about_doc_exists(rel: str):
    """Standard and Algorithmic files have an `__about/` doc."""
    path = about_path(rel)
    assert path.exists(), (
        f"{rel} has no description doc.\n"
        f"Expected: {path.relative_to(PROJECT_ROOT).as_posix()}"
    )


@pytest.mark.parametrize("rel", sorted(FLOW_REQUIRED))
def test_flow_doc_exists(rel: str):
    """Algorithmic files also have a `__flow/` doc."""
    path = flow_path(rel)
    assert path.exists(), (
        f"{rel} is Algorithmic tier but has no flow doc.\n"
        f"Expected: {path.relative_to(PROJECT_ROOT).as_posix()}"
    )


@pytest.mark.parametrize("rel", sorted(TRIVIAL))
def test_trivial_files_have_no_own_docs(rel: str):
    """Trivial tier documents as ONE LINE in the folder doc — nothing more.

    Deleting a useless doc is progress, not loss.
    """
    strays = [
        p.relative_to(PROJECT_ROOT).as_posix()
        for p in (about_path(rel), flow_path(rel))
        if p.exists()
    ]
    assert not strays, (
        f"{rel} is Trivial tier and must have no own docs — delete: {strays}"
    )


@pytest.mark.parametrize("rel", sorted(set(documented_files()) - FLOW_REQUIRED))
def test_standard_files_have_no_flow_doc(rel: str):
    """A flow doc must EARN its place: no diagrams that just restate the code."""
    path = flow_path(rel)
    assert not path.exists(), (
        f"{rel} is Standard tier but has a flow doc at "
        f"{path.relative_to(PROJECT_ROOT).as_posix()}.\n"
        "Either promote it to FLOW_REQUIRED in this test (with a reason), or "
        "delete the flow doc."
    )


# ══════════════════════════════ FOLDER DOCS ══════════════════════════════

@pytest.mark.parametrize("folder,doc", sorted(FOLDER_DOCS.items()))
def test_folder_doc_exists(folder: str, doc: str):
    """Every documented code folder has its `___folder.md` entry point."""
    assert (PROJECT_ROOT / doc).exists(), f"{folder}/ has no folder doc — expected {doc}"


def test_no_orphan_docs():
    """Every `__about/` and `__flow/` doc describes a file that exists."""
    orphans = []
    for kind in ("__about", "__flow"):
        for doc in PROJECT_ROOT.rglob(f"{kind}/*.md"):
            if set(doc.relative_to(PROJECT_ROOT).parts) & EXCLUDED_DIRS:
                continue
            source = doc.parent.parent / f"{doc.stem}.py"
            if not source.exists():
                orphans.append(doc.relative_to(PROJECT_ROOT).as_posix())
    assert not orphans, (
        "these docs describe a script that does not exist (basename must match "
        "the script):\n  " + "\n  ".join(sorted(orphans))
    )


def test_no_legacy_beside_script_docs():
    """MD-First 1.0 left docs beside scripts; 2.0 puts them in `__about/`."""
    legacy = []
    for doc in PROJECT_ROOT.rglob("*.md"):
        rel = doc.relative_to(PROJECT_ROOT)
        if set(rel.parts) & EXCLUDED_DIRS:
            continue
        if doc.parent.name in ("__about", "__flow") or doc.name.startswith("___"):
            continue
        if (doc.parent / f"{doc.stem}.py").exists():
            legacy.append(rel.as_posix())
    assert not legacy, (
        "legacy beside-script docs remain — move them into `__about/`:\n  "
        + "\n  ".join(sorted(legacy))
    )

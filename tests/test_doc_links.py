"""THE DOCS LAW guard, part 1 — the navigation chain.

From `README.md` every `.md` file in the project must be reachable by
following relative links, and no relative link may be broken. A doc nobody can
reach is a doc nobody reads; a broken link is a lie about where something is.

Stated exceptions, encoded here rather than left silent:

- **Excluded directories** — `.claude/`, `UV/` (the owner's gitignored inbox),
  caches and build outputs are neither walked nor required.
- **Links INTO `UV/`** are not asserted: the target set is volatile by design.
- **Monorepo-root docs** (`rules/CODE.md`, `DESIGN.md`, …) are referenced as
  plain backticked text, never as markdown links — a project-level guard
  cannot assert a target outside the project, so such links would falsely
  pass or fail. This test therefore ignores any link that climbs above the
  project root.
- **EXEMPT** — `.md` files that are DATA rather than documentation. None in
  this project today; the list exists so a future fixture is declared, not
  silently skipped.
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROOT_DOC = PROJECT_ROOT / "README.md"

EXCLUDED_DIRS = {
    "build", "dist", "exe", "__pycache__", ".git", ".claude",
    "venv", ".venv", "node_modules", "UV", ".pytest_cache",
}

# Data .md files (fixtures, sample sheets) — documentation-exempt.
EXEMPT: set[str] = set()

# [text](target) — not images (![...]), target captured up to any anchor.
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def all_docs() -> list[Path]:
    """Every documentation .md file in the project."""
    return sorted(
        path
        for path in PROJECT_ROOT.rglob("*.md")
        if not (set(path.relative_to(PROJECT_ROOT).parts) & EXCLUDED_DIRS)
        and path.relative_to(PROJECT_ROOT).as_posix() not in EXEMPT
    )


def links_in(doc: Path) -> list[str]:
    """Raw link targets written inside one document."""
    return LINK.findall(doc.read_text(encoding="utf-8"))


def resolve(doc: Path, target: str) -> Path | None:
    """Resolve one link target to a project path, or None when not our business.

    None means: external URL, pure anchor, a mail link, a path into the
    owner's UV/ inbox, or a path that climbs above the project root (a
    monorepo-root doc, which a project-level guard cannot assert).
    """
    if not target or target.startswith(("http://", "https://", "#", "mailto:")):
        return None
    path = target.split("#", 1)[0]
    if not path:
        return None
    resolved = (doc.parent / path).resolve()
    try:
        relative = resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        return None  # outside the project — not assertable from here
    if set(relative.parts) & {"UV"}:
        return None
    return resolved


def walk_from_readme() -> set[Path]:
    """Every .md reachable from README.md by following relative links."""
    seen: set[Path] = {ROOT_DOC.resolve()}
    queue = [ROOT_DOC]
    while queue:
        doc = queue.pop()
        for target in links_in(doc):
            resolved = resolve(doc, target)
            if resolved is None or resolved.suffix.lower() != ".md":
                continue
            if resolved in seen or not resolved.exists():
                continue
            seen.add(resolved)
            queue.append(resolved)
    return seen


def test_readme_exists():
    assert ROOT_DOC.exists(), "the navigation chain has no root: README.md is missing"


@pytest.mark.parametrize("doc", all_docs(), ids=lambda p: p.name)
def test_no_broken_links(doc: Path):
    """Every relative link in every doc points at something that exists."""
    broken = []
    for target in links_in(doc):
        resolved = resolve(doc, target)
        if resolved is not None and not resolved.exists():
            broken.append(f"{target}  ->  {resolved}")

    assert not broken, (
        f"{doc.relative_to(PROJECT_ROOT).as_posix()}: broken relative links:\n  "
        + "\n  ".join(broken)
    )


def test_every_doc_is_reachable_from_readme():
    """No orphans: README.md reaches every documentation file."""
    reachable = walk_from_readme()
    orphans = [
        doc.relative_to(PROJECT_ROOT).as_posix()
        for doc in all_docs()
        if doc.resolve() not in reachable
    ]
    assert not orphans, (
        "these docs cannot be reached from README.md by following links — "
        "link them from their folder doc, and the folder doc from README:\n  "
        + "\n  ".join(orphans)
    )

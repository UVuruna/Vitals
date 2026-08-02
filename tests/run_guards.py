"""Fast guard runner — what the Claude Code hooks call.

Runs the four guard tests and exits **2** on failure. Exit 2 is what makes a
hook BLOCKING: anything else and the agent sails past a red guard.

    python tests/run_guards.py            all four guards   (Stop hook)
    python tests/run_guards.py --fast     structure + config only (PostToolUse)

Guards only, never the app's own suite: this runs after every single Edit, so
it has to stay well under a couple of seconds and be perfectly deterministic.

In `--fast` mode the runner reads the hook's JSON payload from stdin and exits
0 IMMEDIATELY when the edited file is not Python — a docs session must not pay
the guard cost hundreds of times for markdown edits.
"""

import json
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent

FAST_GUARDS = ["test_structure_law.py", "test_config_sections.py"]
DOC_GUARDS = ["test_docs_coverage.py", "test_doc_links.py"]

FAIL_EXIT_CODE = 2  # a hook only blocks on exit 2


def edited_file_from_stdin() -> str | None:
    """The file path in the hook payload on stdin, or None if there is none."""
    if sys.stdin is None or sys.stdin.isatty():
        return None
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return None
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    return path if isinstance(path, str) else None


def main() -> int:
    fast = "--fast" in sys.argv

    if fast:
        edited = edited_file_from_stdin()
        # Non-source edit (docs, config, anything else): the fast guards have
        # nothing to say about it, so cost nothing.
        if edited is not None and not edited.endswith(".py"):
            return 0

    guards = FAST_GUARDS if fast else FAST_GUARDS + DOC_GUARDS
    targets = [str(TESTS_DIR / name) for name in guards if (TESTS_DIR / name).exists()]

    missing = [name for name in guards if not (TESTS_DIR / name).exists()]
    if missing:
        print(
            "GUARD SETUP ERROR: missing guard test(s): " + ", ".join(missing),
            file=sys.stderr,
        )
        return FAIL_EXIT_CODE

    result = pytest.main(["-q", "--no-header", "-p", "no:cacheprovider", *targets])
    if result != 0:
        print(
            "\nBLOCKED by a guard test. Fix the violation above — a guard is a "
            "law, not a suggestion (see `rules/CODE.md`).",
            file=sys.stderr,
        )
        return FAIL_EXIT_CODE
    return 0


if __name__ == "__main__":
    sys.exit(main())

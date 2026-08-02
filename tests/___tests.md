# tests/

The enforcement layer for THE STRUCTURE LAW, THE CONFIG SECTION LAW and THE
DOCS LAW — four `pytest` guard modules plus a fast wrapper the Claude Code
hooks call. These are static-analysis guards: they scan the project tree
directly (via `pathlib`/`ast`/regex) rather than importing or exercising
`app/`, so a violation is caught the moment it lands, not at a later manual
review.

## Files

| File | Tier | One line |
|------|------|----------|
| `test_structure_law.py` | Trivial (test module) | THE STRUCTURE LAW — fails on any hand-written `.py` file over 1,000 lines outside the RATCHET allowlist |
| `test_config_sections.py` | Trivial (test module) | THE CONFIG SECTION LAW — banner placement, duplicate dict keys, post-definition patching in `app/styles.py` / `app/theme.py` |
| `test_docs_coverage.py` | Trivial (test module) | THE DOCS LAW, part 2 — every source file carries the doc its TIER (Trivial / Standard / Algorithmic) requires, no orphan or legacy docs |
| `test_doc_links.py` | Trivial (test module) | THE DOCS LAW, part 1 — every doc reachable from `README.md`, no broken relative links |
| `run_guards.py` | Trivial (script) | Fast wrapper the Claude Code hooks call — runs the guards above and exits 2 on any failure |

Test modules get no per-file docs beyond this folder doc — see the shared
MD-First 2.0 conventions this migration follows.

## Connections

### Uses
- none — these guards scan the project tree directly; they do not import
  `app/` or `setup/`

### Used by
- The Claude Code hooks (`.claude/settings.json`), via `run_guards.py` — a
  violation blocks the agent turn (exit code 2) instead of surfacing later
  in a manual review or CI run

## Design Decisions

- **`test_structure_law.py` — THE STRUCTURE LAW.** `test_no_god_files` walks
  every hand-written `.py` file (excluding `build/`, `dist/`, `exe/`,
  `__pycache__/`, `.git/`, `.claude/`, `venv/`, `.venv/`, `node_modules/`,
  `UV/`) and fails if any file over 1,000 lines is not named in the
  `RATCHET` dict. `test_ratchet_entries_are_real` fails the build the moment
  a ratchet entry goes stale — the file no longer exists, has shrunk back
  under the threshold, or carries no reason. **`RATCHET` is currently
  EMPTY** — the 2026-08-02 split session that broke `app/main_window.py`
  (2,085 lines), `app/settings_dialog.py` (1,634) and `app/monitor.py`
  (1,477) into `app/windows/`, `app/dialogs/` and `app/collect/` cleared
  every entry it would otherwise owe. **The ratchet may only SHRINK** —
  adding an entry requires the owner's explicit approval in the same
  session that adds it.
- **`test_config_sections.py` — THE CONFIG SECTION LAW.** Scoped narrowly to
  `CONFIG_FILES = [app/styles.py, app/theme.py]` — the two genuinely
  config-centric modules, not every file that happens to hold a table.
  Fails on: a top-level definition sitting above the file's first section
  banner (only the module docstring, imports and `if TYPE_CHECKING:` are
  exempt); a duplicate key inside any dict literal; or post-definition
  patching of an earlier module-level table (`TABLE[...] = ...`, or
  `.update()`/`.setdefault()`/`.append()`/`.extend()` called on a name
  already assigned at module level). A section banner is one comment line
  with the section name between two runs of 8+ rule characters, e.g.
  `# ═══ SECTION NAME ═══`. This guard reads module-level statements only —
  a config-like table hidden inside a class body is invisible to it, which
  is itself a placement smell to fix by lifting the table out, never a
  reason to widen the guard's scope.
- **`test_doc_links.py` — THE DOCS LAW, part 1.** `test_readme_exists`
  requires a root `README.md`. `test_no_broken_links` checks every relative
  link in every `.md` file resolves to something that exists — links that
  climb above the project root (monorepo-root docs, referenced as backticked
  plain text, never as markdown links, since a project-level guard cannot
  assert a target outside the project), external URLs, anchors, and links
  into the owner's gitignored `UV/` inbox are all out of scope by design.
  `test_every_doc_is_reachable_from_readme` walks every relative link
  starting from `README.md` and fails if any `.md` file in the project is
  unreachable — a doc nobody can reach is a doc nobody reads.
- **`test_docs_coverage.py` — THE DOCS LAW, part 2.** Every source file must
  carry the doc its TIER requires, and no more:

  | Tier | Obligation |
  |------|------------|
  | Trivial | one line in the folder doc — NO own docs (an extra doc fails) |
  | Standard | `__about/{name}.md` |
  | Algorithmic | `__about/{name}.md` **and** `__flow/{name}.md` |
  | tests | this folder doc only |

  The tier lists ARE the tier assignment — `TRIVIAL` names the four
  `__init__.py` files, `FLOW_REQUIRED` names exactly 13 of the project's 46
  source files (a flow doc must EARN its place: *would the diagram just
  restate the code?* — then it is Standard, per the owner's 2026-08-01
  decision), everything else owes only an `__about/` doc. `FOLDER_DOCS` maps
  six folders (`app`, `app/collect`, `app/dialogs`, `app/windows`, `setup`,
  `tests`) to the `___folder.md` each must have — the project ROOT is
  deliberately absent from that map, since `main.py` sits directly in it and
  the flat-root rule makes `README.md` play the folder-doc role there.
  Beyond the tier/coverage checks, this guard also fails on an orphan doc
  (an `__about/`/`__flow/` file whose matching `.py` no longer exists) and
  on a legacy MD-First 1.0 doc left sitting beside its script instead of
  moved into `__about/`. Changing a file's TIER means editing the lists in
  this module in the same commit — the tier is a decision recorded here, not
  a fact the guard infers on its own.
- **`run_guards.py` is the fast entry point the Claude Code hooks actually
  call**, not raw `pytest`, so a hook does not pay full test-collection
  overhead on every relevant tool call. `python tests/run_guards.py` (no
  arguments) runs all four guards — this is the **Stop hook**.
  `python tests/run_guards.py --fast` runs only the two SOURCE guards,
  `test_structure_law.py` and `test_config_sections.py` — this is the
  **PostToolUse hook**, which also reads the hook's JSON payload off stdin
  and exits `0` immediately when the edited file is not `.py`, so a pure
  documentation session (like this one) never pays the guard's cost. Either
  mode exits with status `2` on any failure — the code Claude Code hooks
  treat as BLOCKING, surfaced back to the agent — never status `1`, which
  most hook configurations would treat as fire-and-forget.

# CLAUDE.md

**Read `AGENTS.md` first — it is the canonical workflow for building models in
this repo.** Everything below is Claude-specific addenda.

- **Look at your work.** After every `build_model` run, Read the
  `models/<name>/output/*_preview.png` contact sheet and visually compare it
  to `spec.md` before declaring success. This is the core of the loop.
- Interpreter: `.venv\Scripts\python` (Python 3.11). Use it for every script
  invocation; do not use the system Python or install packages globally.
- Long SDF builds (final voxel 0.4–0.5) can take 1–3 minutes — run them with
  `run_in_background` and keep working.
- Windows console: keep CLI `print`/`click.echo` output ASCII-only
  (`->` not `→`); cp1252 consoles crash on fancy glyphs. Rich-console output
  is fine.
- When the user asks to run something themselves, give **cmd.exe** syntax.
- The user may hand you reference images for organic models — put copies in
  `models/<name>/refs/`, study them, and iterate previews against them.
- Don't commit without being asked, and run `git rev-parse --show-toplevel`
  first to confirm you're committing to *this* repo and not an enclosing one.

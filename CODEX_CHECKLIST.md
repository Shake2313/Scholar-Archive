# Codex Checklist

Last updated: 2026-03-13

Purpose:
- Keep a durable task list in the repo so work can resume after restarting the CLI.
- Track both completed work and the next high-impact improvements.

Current status:
- `output/` intentionally excluded from review and edits.
- Existing user changes detected in `pipeline.py`; preserve and build on top of them.
- Glossary/DB-based terminology caching was removed because it was not informing translation quality and was adding extra model cost.

Checklist:
- [x] Review `readme_AI` and inspect the code structure outside `output/`.
- [x] Identify high-impact improvements and rank them.
- [x] Create a persistent checklist file in the repository.
- [x] Add startup/preflight validation for model keys and LaTeX/tooling dependencies.
- [x] Let the pipeline continue with partial output when some page transcriptions fail.
- [x] Persist retry state and add a UI button to retry only failed pages.
- [x] Add a Windows launcher exe path for taskbar-friendly startup.
- [x] Manually review a sample generated PDF (`33b_Zeeman_digitalized.pdf`) for visible layout breakage.
- [ ] Split `run_pipeline()` into smaller step functions to reduce orchestration complexity.
- [ ] Move result-loading logic out of `app.py` into smaller helpers.
- [x] Remove glossary extraction, glossary DB storage, glossary UI, and glossary-specific prompt wiring.
- [x] Add small regression tests for helper functions like page-range parsing and page merging.
- [x] Reconcile docs so `README.md` and the real pipeline behavior match.
- [x] Remove redundant `readme_AI` and keep the README as the single source of project intent.

Next action:
- Split `run_pipeline()` into smaller step functions to reduce orchestration complexity.

Completed in this session:
- Saved this checklist at repo root for resume-friendly progress tracking.
- Added a preflight check that reports GenAI, PDF, and LaTeX readiness before long pipeline work starts.
- Added `unittest` coverage for helper functions and partial-output reporting.
- Updated project docs so the backend and preflight behavior are documented consistently.
- Removed `readme_AI` and moved the core historical-fidelity stance into `README.md`.
- Added partial-success handling so failed transcription pages are skipped instead of aborting the whole run.
- Added per-run pipeline state so the UI can retry only failed pages later.
- Added `launcher.py`, `build_launcher.bat`, and built `ScholarArchive.exe` for Windows launcher use.
- Updated the sidebar rights metadata inputs so they reset on new uploads and reload from saved output metadata.
- Visually checked `output/33b_Zeeman/33b_Zeeman_digitalized.pdf` against the source scan for font size, spacing, equations, footnotes, and the last-page whitespace.
- Removed glossary generation, glossary reuse, glossary backup, and glossary tab rendering.
- Simplified the translation prompt so Korean translation works directly from the digitalized LaTeX without glossary handoff.
- Removed `glossary_db.py`, deleted the local `glossary.db`, and dropped glossary-specific tests.

Verification:
- `python -m py_compile pipeline.py app.py steps.py prompts.py`
- `python -m py_compile launcher.py`
- `python -c "from steps import run_preflight_checks; ..."` returned `pdf=ok`, `latex=ok`, and a non-blocking `genai=warn` in the plain shell context.
- `python -m PyInstaller ... launcher.py` built `ScholarArchive.exe` in the repo root.
- `python -m unittest discover -s tests -p "test_*.py" -v` passes after removing glossary-specific coverage.
- `python -m py_compile app.py` passed after the sidebar metadata auto-update change.
- Manual PDF QA result for `output/33b_Zeeman/33b_Zeeman_digitalized.pdf`: no obvious clipping, overlap, equation breakage, or footnote loss; last-page whitespace matches the source structure; remaining gap is historical-faithfulness tuning rather than PDF corruption.

Notes for resume:
- Main orchestration lives in `pipeline.py`.
- Shared execution helpers live in `steps.py`.
- The Streamlit UI is in `app.py`.
- The next high-value target is structural refactoring of `run_pipeline()`.

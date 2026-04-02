import io
import json
import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path

from backend.pipeline import (
    apply_manual_metadata_override,
    assess_rights,
    build_metadata_report,
    build_effective_metadata,
    build_rights_metadata,
    collect_cached_image_paths,
    chunked,
    extract_json_object,
    find_first_cached_page_artifacts,
    load_metadata_context,
    load_pipeline_state,
    load_metadata_report,
    normalize_ai_metadata,
    normalize_recorded_ai_metadata,
    normalize_page_numbers,
    page_image_path,
    parse_page_range,
    pipeline_stderr_log_path,
    pipeline_state_path,
    pipeline_stdout_log_path,
    preflight_kwargs_for_run_mode,
    refresh_metadata_outputs,
    redirect_pipeline_output,
    resolve_requested_page_numbers,
    resolve_run_mode,
    render_metadata_prompt,
    RUN_MODE_FULL,
    RUN_MODE_KOREAN_PDF_ONLY,
    RUN_MODE_METADATA_ONLY,
    RUN_MODE_TRANSLATION_ONLY,
    save_rights_report,
    save_pipeline_state,
    should_include_page_in_merge,
    should_reuse_cached_page,
    split_latex_into_page_docs,
)
from backend.publish import (
    build_publish_bundle,
    build_publish_bundle_from_existing_output,
    century_label,
    latex_to_readable_text,
    slugify,
    storage_relative_path,
    write_metadata_override,
)
from backend.steps import (
    _apply_common_compile_fix,
    _latex_compile_timeout_sec,
    _request_http_options,
    apply_source_layout_profile,
    finalize_report,
    merge_pages,
    prepare_latex_for_compile,
)


class PipelineHelperTests(unittest.TestCase):
    def make_workspace_dir(self):
        root = Path(__file__).resolve().parent / ".tmp"
        root.mkdir(exist_ok=True)
        path = root / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return str(path)

    def test_parse_page_range_mixed_values(self):
        self.assertEqual(parse_page_range("1-3,5", 5), [0, 1, 2, 4])

    def test_parse_page_range_filters_out_of_bounds(self):
        self.assertEqual(parse_page_range("4,2,7", 4), [3, 1])

    def test_chunked_groups_items_by_size(self):
        self.assertEqual(chunked([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

    def test_chunked_non_positive_size_returns_single_chunk(self):
        self.assertEqual(chunked([1, 2, 3], 0), [[1, 2, 3]])

    def test_resolve_run_mode_defaults_to_full(self):
        self.assertEqual(resolve_run_mode(), RUN_MODE_FULL)

    def test_resolve_run_mode_returns_selected_stage_only_mode(self):
        self.assertEqual(resolve_run_mode(metadata_only=True), RUN_MODE_METADATA_ONLY)
        self.assertEqual(resolve_run_mode(translation_only=True), RUN_MODE_TRANSLATION_ONLY)
        self.assertEqual(resolve_run_mode(korean_pdf_only=True), RUN_MODE_KOREAN_PDF_ONLY)

    def test_resolve_run_mode_rejects_multiple_stage_flags(self):
        with self.assertRaises(ValueError):
            resolve_run_mode(metadata_only=True, translation_only=True)

    def test_preflight_kwargs_for_run_mode_match_stage_requirements(self):
        self.assertEqual(
            preflight_kwargs_for_run_mode(RUN_MODE_METADATA_ONLY),
            {"needs_genai": True, "needs_pdf": False, "latex_compilers": ()},
        )
        self.assertEqual(
            preflight_kwargs_for_run_mode(RUN_MODE_TRANSLATION_ONLY),
            {"needs_genai": True, "needs_pdf": False, "latex_compilers": ()},
        )
        self.assertEqual(
            preflight_kwargs_for_run_mode(RUN_MODE_KOREAN_PDF_ONLY),
            {"needs_genai": False, "needs_pdf": False, "latex_compilers": ("xelatex",)},
        )

    def test_normalize_page_numbers_filters_invalid_values(self):
        self.assertEqual(normalize_page_numbers([3, "2", 2, 0, -1, "x"]), [3, 2])

    def test_find_first_cached_page_artifacts_prefers_candidate_page_order(self):
        tmpdir = Path(self.make_workspace_dir())
        (tmpdir / "page_002_structure.json").write_text("{}", encoding="utf-8")
        (tmpdir / "page_002.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nPage two\n\\end{document}\n",
            encoding="utf-8",
        )
        (tmpdir / "page_001_structure.json").write_text("{}", encoding="utf-8")
        (tmpdir / "page_001.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nPage one\n\\end{document}\n",
            encoding="utf-8",
        )

        page_num, structure_json, latex_source = find_first_cached_page_artifacts(
            str(tmpdir),
            [2, 1],
        )
        self.assertEqual(page_num, 2)
        self.assertEqual(structure_json, "{}")
        self.assertIn("Page two", latex_source)

    def test_collect_cached_image_paths_requires_all_requested_pages(self):
        tmpdir = Path(self.make_workspace_dir())
        images_dir = tmpdir / "images"
        images_dir.mkdir()
        image1 = Path(page_image_path(str(images_dir), 1))
        image2 = Path(page_image_path(str(images_dir), 2))
        image1.write_bytes(b"png1")
        image2.write_bytes(b"png2")

        self.assertEqual(
            collect_cached_image_paths(str(images_dir), [1, 2]),
            [str(image1), str(image2)],
        )
        image2.unlink()
        self.assertEqual(collect_cached_image_paths(str(images_dir), [1, 2]), [])

    def test_load_metadata_report_round_trips_saved_json(self):
        tmpdir = self.make_workspace_dir()
        report = {
            "raw_pdf_metadata": {"title": "Demo"},
            "deterministic_inference": {"title": "Demo"},
            "ai_inference": {"title": "Demo", "status": "ok", "error": None},
        }
        path = Path(tmpdir) / "demo_metadata.json"
        path.write_text('{"raw_pdf_metadata":{"title":"Demo"},"deterministic_inference":{"title":"Demo"},"ai_inference":{"title":"Demo","status":"ok","error":null}}', encoding="utf-8")
        self.assertEqual(load_metadata_report(tmpdir, "demo"), report)

    def test_load_metadata_context_reuses_cached_report(self):
        tmpdir = self.make_workspace_dir()
        report = build_metadata_report(
            name="demo",
            raw_pdf_metadata={"title": "Cached raw"},
            deterministic_metadata={
                "title": "Cached title",
                "author": "Cached author",
                "publication_year": 1918,
                "death_year": None,
            },
            ai_metadata={
                "title": "AI title",
                "author": "AI author",
                "publication_year": 1918,
                "death_year": None,
                "journal_or_book": None,
                "volume": None,
                "issue": None,
                "pages": None,
                "language": None,
                "doi": None,
                "confidence": {field: "none" for field in (
                    "title",
                    "author",
                    "publication_year",
                    "death_year",
                    "journal_or_book",
                    "volume",
                    "issue",
                    "pages",
                    "language",
                    "doi",
                )},
                "evidence": {},
                "status": "ok",
                "error": None,
            },
            manual_override={"author": "Manual author"},
            effective_metadata={"title": "Effective title"},
            effective_sources={"title": "structure"},
            rights_metadata={"author": "Rights author"},
            rights_sources={"author": "structure"},
        )
        write_metadata_override(tmpdir, "demo", {"author": "Manual author"})
        Path(tmpdir, "demo_metadata.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        (
            raw_pdf_metadata,
            deterministic_metadata,
            ai_metadata,
            manual_override,
            metadata_report_reused,
        ) = load_metadata_context(
            output_dir=tmpdir,
            name="demo",
            source_pdf_path=None,
            resume=True,
            force_refresh_metadata=False,
        )

        self.assertEqual(raw_pdf_metadata["title"], "Cached raw")
        self.assertEqual(deterministic_metadata["author"], "Cached author")
        self.assertEqual(ai_metadata["status"], "ok")
        self.assertEqual(manual_override["author"], "Manual author")
        self.assertTrue(metadata_report_reused)

    def test_refresh_metadata_outputs_saves_report_and_manual_override(self):
        tmpdir = self.make_workspace_dir()
        (
            effective_metadata,
            effective_sources,
            rights_metadata,
            rights_sources,
            metadata_report_path_value,
        ) = refresh_metadata_outputs(
            output_dir=tmpdir,
            name="demo",
            author=None,
            publication_year=None,
            death_year=None,
            raw_pdf_metadata={"title": "Raw title"},
            deterministic_metadata={
                "title": "Structured title",
                "author": "Structured author",
                "publication_year": 1918,
                "death_year": None,
            },
            ai_metadata=normalize_recorded_ai_metadata({}),
            manual_override={"author": "Manual author"},
        )

        self.assertEqual(effective_metadata["title"], "Raw title")
        self.assertEqual(effective_metadata["author"], "Manual author")
        self.assertEqual(effective_sources["author"], "manual_override")
        self.assertEqual(rights_metadata["author"], "Manual author")
        self.assertEqual(rights_sources["author"], "manual_override")
        self.assertTrue(Path(metadata_report_path_value).is_file())
        saved_report = load_metadata_report(tmpdir, "demo")
        self.assertEqual(saved_report["manual_override"]["author"], "Manual author")
        self.assertEqual(saved_report["effective_metadata"]["author"], "Manual author")

    def test_save_rights_report_persists_source_summary(self):
        tmpdir = self.make_workspace_dir()
        rights_info, rights_path = save_rights_report(
            tmpdir,
            "demo",
            "Jean Le Rond D'Alembert",
            1750,
            None,
            sources={"author": "structure", "publication_year": "ai_high"},
        )
        saved = json.loads(Path(rights_path).read_text(encoding="utf-8"))
        self.assertEqual(saved["assessment"], "likely_public_domain_us")
        self.assertTrue(saved["needs_manual_review"])
        self.assertIn("publication_year=ai_high", saved["source_summary"])
        self.assertEqual(saved["assessment"], rights_info["assessment"])

    def test_resolve_requested_page_numbers_handles_retry_and_all_pages(self):
        page_numbers, retry_page_numbers, requested_page_numbers = resolve_requested_page_numbers(
            total_input_pages=5,
            pages=None,
            retry_pages="2,4",
            state_requested_pages=[1, 2, 3, 4],
        )
        self.assertEqual(page_numbers, [1, 3])
        self.assertEqual(retry_page_numbers, {2, 4})
        self.assertEqual(requested_page_numbers, [1, 2, 3, 4])

        page_numbers, retry_page_numbers, requested_page_numbers = resolve_requested_page_numbers(
            total_input_pages=3,
            pages=None,
            retry_pages=None,
            state_requested_pages=None,
        )
        self.assertIsNone(page_numbers)
        self.assertEqual(retry_page_numbers, set())
        self.assertEqual(requested_page_numbers, [1, 2, 3])

    def test_normalize_recorded_ai_metadata_preserves_status_and_error(self):
        normalized = normalize_recorded_ai_metadata(
            {"title": "Demo", "status": "empty", "error": "bad json"}
        )
        self.assertEqual(normalized["title"], "Demo")
        self.assertEqual(normalized["status"], "empty")
        self.assertEqual(normalized["error"], "bad json")

    def test_redirect_pipeline_output_writes_standard_logs(self):
        tmpdir = self.make_workspace_dir()
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        with redirect_pipeline_output(
            tmpdir,
            "demo",
            stdout_stream=stdout_capture,
            stderr_stream=stderr_capture,
        ):
            print("hello stdout")
            print("hello stderr", file=sys.stderr)

        stdout_log = Path(pipeline_stdout_log_path(tmpdir, "demo")).read_text(encoding="utf-8")
        stderr_log = Path(pipeline_stderr_log_path(tmpdir, "demo")).read_text(encoding="utf-8")
        self.assertIn("hello stdout", stdout_capture.getvalue())
        self.assertIn("hello stderr", stderr_capture.getvalue())
        self.assertIn("hello stdout", stdout_log)
        self.assertIn("hello stderr", stderr_log)

    def test_should_reuse_cached_page_skips_explicit_retry_pages(self):
        tmpdir = Path(self.make_workspace_dir())
        struct_path = tmpdir / "page_001_structure.json"
        tex_path = tmpdir / "page_001.tex"
        struct_path.write_text("{}", encoding="utf-8")
        tex_path.write_text("\\documentclass{article}", encoding="utf-8")

        self.assertFalse(
            should_reuse_cached_page(
                resume=True,
                page_num=1,
                retry_page_numbers={1},
                struct_path=str(struct_path),
                tex_path=str(tex_path),
            )
        )
        self.assertTrue(
            should_reuse_cached_page(
                resume=True,
                page_num=2,
                retry_page_numbers={1},
                struct_path=str(struct_path),
                tex_path=str(tex_path),
            )
        )

    def test_should_include_page_in_merge_excludes_current_failures(self):
        self.assertFalse(should_include_page_in_merge(1, {1: {"error": "timeout"}}))
        self.assertTrue(should_include_page_in_merge(2, {1: {"error": "timeout"}}))

    def test_extract_json_object_handles_fenced_json(self):
        payload = extract_json_object("```json\n{\"title\":\"Demo\",\"publication_year\":1918}\n```")
        self.assertEqual(payload["title"], "Demo")
        self.assertEqual(payload["publication_year"], 1918)

    def test_render_metadata_prompt_preserves_example_json_braces(self):
        prompt = render_metadata_prompt(
            paper_name="Demo",
            raw_pdf_metadata_json='{"title": "Raw"}',
            structure_json='{"article_header": {"title_text": "Demo"}}',
            first_page_latex="\\begin{document}Demo\\end{document}",
        )
        self.assertIn('"title": "<string or null>"', prompt)
        self.assertIn("PAPER NAME HINT:\nDemo", prompt)
        self.assertIn('RAW PDF METADATA:\n{"title": "Raw"}', prompt)

    def test_normalize_ai_metadata_coerces_confidence_and_years(self):
        normalized = normalize_ai_metadata(
            {
                "title": " Demo ",
                "publication_year": "Published in 1750",
                "confidence": {"title": "HIGH"},
                "evidence": {"title": "header"},
            }
        )
        self.assertEqual(normalized["title"], "Demo")
        self.assertEqual(normalized["publication_year"], 1750)
        self.assertEqual(normalized["confidence"]["title"], "high")
        self.assertEqual(normalized["confidence"]["publication_year"], "low")
        self.assertEqual(normalized["evidence"]["title"], "header")

    def test_build_effective_metadata_uses_ai_for_missing_fields(self):
        effective, sources = build_effective_metadata(
            None,
            None,
            None,
            {"title": None, "author": None},
            {"title": None, "author": "Jean le Rond d'Alembert", "publication_year": None, "death_year": None},
            {
                "title": "Recherches sur la courbe",
                "author": "Jean le Rond d'Alembert",
                "publication_year": 1750,
                "death_year": 1783,
                "journal_or_book": "Histoire de l'Académie royale des sciences et belles-lettres de Berlin",
                "volume": None,
                "issue": None,
                "pages": "214-219",
                "language": "French",
                "doi": None,
                "confidence": {
                    "title": "high",
                    "author": "high",
                    "publication_year": "medium",
                    "death_year": "medium",
                    "journal_or_book": "medium",
                    "volume": "none",
                    "issue": "none",
                    "pages": "medium",
                    "language": "medium",
                    "doi": "none",
                },
                "evidence": {},
            },
        )
        self.assertEqual(effective["title"], "Recherches sur la courbe")
        self.assertEqual(effective["author"], "Jean le Rond d'Alembert")
        self.assertEqual(effective["publication_year"], 1750)
        self.assertEqual(effective["journal_or_book"], "Histoire de l'Académie royale des sciences et belles-lettres de Berlin")
        self.assertEqual(sources["title"], "ai")
        self.assertEqual(sources["author"], "structure")

    def test_build_rights_metadata_requires_high_confidence_for_ai_years(self):
        rights, sources = build_rights_metadata(
            None,
            None,
            None,
            {},
            {"title": None, "author": None, "publication_year": None, "death_year": None},
            {
                "title": None,
                "author": "Anonymous",
                "publication_year": 1918,
                "death_year": 1999,
                "journal_or_book": None,
                "volume": None,
                "issue": None,
                "pages": None,
                "language": None,
                "doi": None,
                "confidence": {
                    "title": "none",
                    "author": "high",
                    "publication_year": "medium",
                    "death_year": "low",
                    "journal_or_book": "none",
                    "volume": "none",
                    "issue": "none",
                    "pages": "none",
                    "language": "none",
                    "doi": "none",
                },
                "evidence": {},
            },
        )
        self.assertEqual(rights["author"], "Anonymous")
        self.assertIsNone(rights["publication_year"])
        self.assertIsNone(rights["death_year"])
        self.assertEqual(sources["author"], "ai_high")

    def test_assess_rights_flags_ai_inferred_public_domain_for_manual_review(self):
        rights = assess_rights(
            "Jean Le Rond D'Alembert",
            1750,
            None,
            sources={"publication_year": "ai_high", "author": "structure"},
        )
        self.assertEqual(rights["assessment"], "likely_public_domain_us")
        self.assertEqual(rights["basis"], "publication_year")
        self.assertTrue(rights["needs_manual_review"])
        self.assertIn("AI-inferred metadata", rights["reason"])

    def test_assess_rights_accepts_direct_death_year_without_review_flag(self):
        rights = assess_rights(
            "Emmy Noether",
            None,
            1935,
            sources={"author": "user", "death_year": "user"},
        )
        self.assertEqual(rights["assessment"], "likely_public_domain_life_plus_70")
        self.assertEqual(rights["basis"], "death_year")
        self.assertFalse(rights["needs_manual_review"])
        self.assertEqual(rights["warnings"], [])

    def test_apply_manual_metadata_override_replaces_effective_and_rights_values(self):
        effective, effective_sources, rights, right_sources = apply_manual_metadata_override(
            {"title": "Auto Title", "author": "Auto Author", "publication_year": 1918},
            {"title": "ai", "author": "ai", "publication_year": "structure"},
            {"author": "Auto Author", "publication_year": 1918, "death_year": None},
            {"author": "ai_high", "publication_year": "structure", "death_year": None},
            {"title": "Manual Title", "author": "Manual Author", "publication_year": 1919},
        )
        self.assertEqual(effective["title"], "Manual Title")
        self.assertEqual(effective["author"], "Manual Author")
        self.assertEqual(effective["publication_year"], 1919)
        self.assertEqual(effective_sources["title"], "manual_override")
        self.assertEqual(rights["author"], "Manual Author")
        self.assertEqual(rights["publication_year"], 1919)
        self.assertEqual(right_sources["publication_year"], "manual_override")

    def test_split_latex_into_page_docs_preserves_document_wrapper(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "Page one\n"
            "\\newpage\n"
            "Page two\n"
            "\\end{document}\n"
        )
        docs = split_latex_into_page_docs(source)
        self.assertEqual(len(docs), 2)
        self.assertTrue(all("\\documentclass{article}" in doc for doc in docs))
        self.assertTrue(all(doc.strip().endswith("\\end{document}") for doc in docs))
        self.assertIn("Page one", docs[0])
        self.assertIn("Page two", docs[1])

    def test_merge_pages_joins_document_bodies(self):
        page_a = "\\documentclass{article}\n\\begin{document}\nA\n\\end{document}\n"
        page_b = "\\documentclass{article}\n\\begin{document}\nB\n\\end{document}\n"
        merged = merge_pages([page_a, page_b])
        self.assertIn("A", merged)
        self.assertIn("B", merged)
        self.assertIn("\\newpage", merged)
        self.assertEqual(merged.count("\\begin{document}"), 1)
        self.assertEqual(merged.count("\\end{document}"), 1)

    def test_prepare_latex_for_compile_normalizes_symbolic_footnotes(self):
        source = (
            "\\documentclass{article}\n"
            "\\usepackage[symbol*]{footmisc}\n"
            "\\begin{document}\n"
            "Title\\footnotemark[*]\n"
            "\\footnotetext[*]{Note}\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="pdflatex")
        self.assertIn("\\footnotemark[1]", prepared)
        self.assertIn("\\footnotetext[1]", prepared)
        self.assertNotIn("\\footnotemark[*]", prepared)

    def test_prepare_latex_for_compile_adds_graphicx_when_needed(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\scalebox{2}[1]{=}\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="xelatex")
        self.assertIn("\\usepackage{graphicx}", prepared)

    def test_prepare_latex_for_compile_adds_wrapfig_when_needed(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\begin{wrapfigure}{r}{0.3\\textwidth}\n"
            "X\n"
            "\\end{wrapfigure}\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="pdflatex")
        self.assertIn("\\usepackage{wrapfig}", prepared)

    def test_prepare_latex_for_compile_adds_tikz_when_needed(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\begin{tikzpicture}\n"
            "\\draw (0,0) -- (1,1);\n"
            "\\end{tikzpicture}\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="pdflatex")
        self.assertIn("\\usepackage{tikz}", prepared)

    def test_prepare_latex_for_compile_adds_amsmath_for_align_and_text(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\begin{align*}\n"
            "f(x) &= \\text{value} + \\dfrac{1}{2}\n"
            "\\end{align*}\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="xelatex")
        self.assertIn("\\usepackage{amsmath}", prepared)

    def test_prepare_latex_for_compile_adds_amssymb_for_mathbb(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "$\\mathbb{R} \\therefore x \\in \\varnothing$\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="xelatex")
        self.assertIn("\\usepackage{amssymb}", prepared)

    def test_prepare_latex_for_compile_adds_mathrsfs_for_mathscr(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "$\\mathscr{L}(x)$\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="xelatex")
        self.assertIn("\\usepackage{mathrsfs}", prepared)

    def test_prepare_latex_for_compile_adds_pdflatex_support_for_long_s(self):
        source = (
            "\\documentclass{article}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\begin{document}\n"
            "compoſé\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="pdflatex")
        self.assertIn("\\usepackage{textcomp}", prepared)
        self.assertIn("\\DeclareTextSymbol{\\textlongs}{TS1}{116}", prepared)
        self.assertIn("\\DeclareTextSymbolDefault{\\textlongs}{TS1}", prepared)
        self.assertIn("\\DeclareUnicodeCharacter{017F}{\\textlongs}", prepared)

    def test_prepare_latex_for_compile_strips_pdflatex_unicode_decl_for_xelatex(self):
        source = (
            "\\documentclass{article}\n"
            "\\usepackage{textcomp}\n"
            "\\DeclareTextSymbol{\\textlongs}{TS1}{116}\n"
            "\\DeclareTextSymbolDefault{\\textlongs}{TS1}\n"
            "\\DeclareUnicodeCharacter{017F}{\\textlongs}\n"
            "\\begin{document}\n"
            "ſ\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="xelatex")
        self.assertNotIn("\\DeclareUnicodeCharacter{017F}{\\textlongs}", prepared)
        self.assertIn("\\DeclareTextSymbol{\\textlongs}{TS1}{116}", prepared)

    def test_prepare_latex_for_compile_defines_longequal_when_missing(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "$a \\longequal b$\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="xelatex")
        self.assertIn("\\providecommand{\\longequal}{=}", prepared)

    def test_prepare_latex_for_compile_defines_coloneqq_fallbacks(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "$a \\coloneqq b, c \\eqqcolon d$\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="xelatex")
        self.assertIn("\\providecommand{\\coloneqq}{\\mathrel{:=}}", prepared)
        self.assertIn("\\providecommand{\\eqqcolon}{\\mathrel{=:}}", prepared)

    def test_request_http_options_uses_millisecond_timeout(self):
        options = _request_http_options()
        self.assertEqual(options.timeout, 180000)
        self.assertEqual(options.retry_options.attempts, 2)
        self.assertEqual(options.retry_options.http_status_codes, [429, 500, 502, 503, 504])

    def test_latex_compile_timeout_has_floor(self):
        original = os.environ.get("LATEX_COMPILE_TIMEOUT_SEC")
        self.addCleanup(
            lambda: os.environ.__setitem__("LATEX_COMPILE_TIMEOUT_SEC", original)
            if original is not None
            else os.environ.pop("LATEX_COMPILE_TIMEOUT_SEC", None)
        )
        os.environ["LATEX_COMPILE_TIMEOUT_SEC"] = "5"
        self.assertEqual(_latex_compile_timeout_sec(), 30)

    def test_prepare_latex_for_compile_wraps_decimal_cdots_in_text(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "The value was 1\\cdot87 inches.\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="xelatex")
        self.assertIn("1$\\cdot$87", prepared)

    def test_apply_common_compile_fix_restores_commented_tikz_for_missing_image(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\begin{wrapfigure}{r}{0.4\\textwidth}\n"
            "    \\includegraphics[width=0.3\\textwidth]{diagram.png}\n"
            "    % \\begin{tikzpicture}[scale=1.2]\n"
            "    %   \\draw (0,0) -- (1,1);\n"
            "    % \\end{tikzpicture}\n"
            "\\end{wrapfigure}\n"
            "\\end{document}\n"
        )
        fixed = _apply_common_compile_fix(
            source,
            "LaTeX Warning: File `diagram.png' not found on input line 4.\n",
            "pdflatex",
        )
        self.assertIsNotNone(fixed)
        self.assertIn("\\usepackage{tikz}", fixed)
        self.assertIn("\\begin{tikzpicture}[scale=1.2]", fixed)
        self.assertNotIn("\\includegraphics[width=0.3\\textwidth]{diagram.png}", fixed)

    def test_apply_common_compile_fix_inserts_placeholder_for_missing_image(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\includegraphics[width=0.25\\textwidth]{missing.png}\n"
            "\\end{document}\n"
        )
        fixed = _apply_common_compile_fix(
            source,
            "LaTeX Warning: File `missing.png' not found on input line 3.\n",
            "pdflatex",
        )
        self.assertIsNotNone(fixed)
        self.assertIn("Source diagram unavailable", fixed)
        self.assertIn("\\parbox[c][8em][c]{0.25\\textwidth}", fixed)

    def test_apply_source_layout_profile_rewrites_font_size_and_geometry(self):
        source = (
            "\\documentclass[10pt]{article}\n"
            "\\usepackage{geometry}\n"
            "\\geometry{top=2.5cm,bottom=2.5cm,left=2.8cm,right=2.8cm,headheight=14pt}\n"
            "\\begin{document}\n"
            "Body\n"
            "\\end{document}\n"
        )
        profile = {
            "page_width_in": 5.87,
            "page_height_in": 8.44,
            "font_size_pt": 12,
            "geometry_options": (
                "paperwidth=422.88bp,paperheight=607.68bp,"
                "top=30.38bp,bottom=30.38bp,left=54.55bp,right=33.83bp,headheight=14pt"
            ),
        }
        updated = apply_source_layout_profile(source, profile)
        self.assertIn("\\documentclass[12pt]{article}", updated)
        self.assertIn("paperwidth=422.88bp", updated)
        self.assertIn("paperheight=607.68bp", updated)
        self.assertIn("left=54.55bp", updated)
        self.assertIn("right=33.83bp", updated)
        self.assertIn("% Auto layout profile: 5.87in x 8.44in, 12pt", updated)

    def test_apply_source_layout_profile_preserves_other_documentclass_options(self):
        source = (
            "\\documentclass[twocolumn,10pt]{article}\n"
            "\\usepackage{geometry}\n"
            "\\begin{document}\n"
            "Body\n"
            "\\end{document}\n"
        )
        profile = {"font_size_pt": 11, "geometry_options": "paperwidth=500bp,paperheight=700bp"}
        updated = apply_source_layout_profile(source, profile)
        self.assertIn("\\documentclass[11pt,twocolumn]{article}", updated)

    def test_slugify_handles_mixed_spacing(self):
        self.assertEqual(slugify("  Recherches sur la courbe  "), "recherches-sur-la-courbe")

    def test_slugify_transliterates_accented_titles(self):
        self.assertEqual(
            slugify("Première partie: loix générales du mouvement"),
            "premiere-partie-loix-generales-du-mouvement",
        )

    def test_slugify_hashes_non_ascii_only_titles(self):
        self.assertTrue(slugify("브룩 테일러").startswith("document-"))

    def test_storage_relative_path_canonicalizes_named_assets(self):
        self.assertEqual(
            storage_relative_path("Traité_de_dynamique CH1_source.pdf", "source_pdf"),
            "source.pdf",
        )

    def test_storage_relative_path_sanitizes_artifacts(self):
        sanitized = storage_relative_path("_review/été compare.png", "artifact")
        self.assertTrue(sanitized.endswith("/ete-compare.png"))
        self.assertTrue(all(ord(ch) < 128 for ch in sanitized))

    def test_century_label_formats_historical_year(self):
        self.assertEqual(century_label(1750), "18th century")

    def test_latex_to_readable_text_removes_wrapper_commands(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\section*{Intro}\n"
            "Text with \\textit{emphasis}.\\\\\n"
            "\\end{document}\n"
        )
        readable = latex_to_readable_text(source)
        self.assertIn("Intro", readable)
        self.assertIn("Text with emphasis.", readable)
        self.assertNotIn("\\textit", readable)

    def test_build_publish_bundle_maps_pages_and_assets(self):
        tmpdir = Path(self.make_workspace_dir())
        output_dir = tmpdir / "demo"
        (output_dir / "images").mkdir(parents=True)
        (output_dir / "demo_source.pdf").write_bytes(b"%PDF-1.4\n")
        (output_dir / "images" / "page_001.png").write_bytes(b"png")
        (output_dir / "page_001.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nPage One\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_001_structure.json").write_text("{}", encoding="utf-8")
        bundle = build_publish_bundle(
            output_dir=str(output_dir),
            name="demo",
            source_pdf_path=str(output_dir / "demo_source.pdf"),
            requested_page_numbers=[1],
            successful_page_numbers=[1],
            effective_metadata={
                "title": "Demo Title",
                "author": "Author Name",
                "publication_year": 1918,
                "death_year": None,
                "journal_or_book": None,
                "volume": None,
                "issue": None,
                "pages": "1-2",
                "language": "French",
                "doi": None,
            },
            rights_info={
                "author": "Author Name",
                "publication_year": 1918,
                "death_year": None,
                "assessment": "likely_public_domain_us",
                "reason": "heuristic",
            },
            raw_pdf_metadata={},
            deterministic_metadata={},
            ai_metadata={},
            layout_profile={"font_size_pt": 10},
            final_dig_latex="\\documentclass{article}\n\\begin{document}\nDigital page\n\\end{document}\n",
            final_kor_latex="\\documentclass{article}\n\\begin{document}\nKorean page\n\\end{document}\n",
        )
        self.assertEqual(bundle["document"]["slug"], "demo-title")
        self.assertEqual(bundle["document"]["century_label"], "20th century")
        self.assertEqual(bundle["pages"][0]["page_number"], 1)
        self.assertEqual(bundle["pages"][0]["digitalized_text"], "Digital page")
        self.assertEqual(bundle["pages"][0]["korean_text"], "Korean page")
        self.assertTrue(any(asset["asset_type"] == "source_pdf" for asset in bundle["assets"]))

    def test_build_publish_bundle_from_existing_output_supports_legacy_runs(self):
        tmpdir = Path(self.make_workspace_dir())
        output_dir = tmpdir / "legacy"
        (output_dir / "images").mkdir(parents=True)
        (output_dir / "legacy_source.pdf").write_bytes(b"%PDF-1.4\n")
        (output_dir / "legacy_digitalized.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nDigital legacy\n\\newpage\nSecond page\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "legacy_Korean.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nKorean legacy\n\\newpage\nSecond Korean page\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_001.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nPage 1\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_002.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nPage 2\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_001_structure.json").write_text(
            '{"article_header":{"title_text":"Legacy Title","author_line":"By Legacy Author"},"footnotes":["Printed in 1918"]}',
            encoding="utf-8",
        )
        (output_dir / "images" / "page_001.png").write_bytes(b"png")
        (output_dir / "images" / "page_002.png").write_bytes(b"png")
        (output_dir / "legacy_pipeline_state.json").write_text(
            '{"requested_pages":[1,2],"successful_pages":[1,2]}',
            encoding="utf-8",
        )

        bundle = build_publish_bundle_from_existing_output(
            output_dir=str(output_dir),
            name="legacy",
        )

        self.assertEqual(bundle["document"]["title"], "Legacy Title")
        self.assertEqual(bundle["document"]["author_display"], "Legacy Author")
        self.assertEqual(bundle["document"]["publication_year"], 1918)
        self.assertEqual(bundle["document"]["century_label"], "20th century")
        self.assertEqual(len(bundle["pages"]), 2)
        self.assertEqual(bundle["pages"][1]["korean_text"], "Second Korean page")


class PipelineStateTests(unittest.TestCase):
    def make_workspace_dir(self):
        root = Path(__file__).resolve().parent / ".tmp"
        root.mkdir(exist_ok=True)
        path = root / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return str(path)

    def test_pipeline_state_round_trip(self):
        tmpdir = self.make_workspace_dir()
        state = {"paper_name": "demo", "failed_pages": [3, 7]}
        save_pipeline_state(tmpdir, "demo", state)
        self.assertEqual(
            pipeline_state_path(tmpdir, "demo"),
            os.path.join(tmpdir, "demo_pipeline_state.json"),
        )
        self.assertEqual(load_pipeline_state(tmpdir, "demo"), state)

    def test_finalize_report_marks_partial_output(self):
        tmpdir = self.make_workspace_dir()
        report_path = finalize_report(
            "demo",
            12,
            True,
            True,
            tmpdir,
            successful_pages=11,
            failed_pages=[12],
        )
        data = Path(report_path).read_text(encoding="utf-8")
        self.assertIn('"successful_pages": 11', data)
        self.assertIn('"failed_pages": [', data)
        self.assertIn('"partial_output": true', data)
        self.assertNotIn('"glossary"', data)


if __name__ == "__main__":
    unittest.main()

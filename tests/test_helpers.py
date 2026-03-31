import os
import shutil
import unittest
import uuid
from pathlib import Path

from pipeline import (
    build_effective_metadata,
    build_rights_metadata,
    chunked,
    extract_json_object,
    load_pipeline_state,
    normalize_ai_metadata,
    parse_page_range,
    pipeline_state_path,
    render_metadata_prompt,
    save_pipeline_state,
    should_include_page_in_merge,
    should_reuse_cached_page,
    split_latex_into_page_docs,
)
from publish import (
    build_publish_bundle,
    build_publish_bundle_from_existing_output,
    century_label,
    latex_to_readable_text,
    slugify,
    storage_relative_path,
)
from steps import (
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
        root = Path(__file__).resolve().parents[1] / "tests_tmp"
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
        root = Path(__file__).resolve().parents[1] / "tests_tmp"
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

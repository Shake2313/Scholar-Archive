import os
import shutil
import unittest
import uuid
from pathlib import Path

from pipeline import (
    chunked,
    load_pipeline_state,
    parse_page_range,
    pipeline_state_path,
    save_pipeline_state,
    split_latex_into_page_docs,
)
from steps import finalize_report, merge_pages, prepare_latex_for_compile


class PipelineHelperTests(unittest.TestCase):
    def test_parse_page_range_mixed_values(self):
        self.assertEqual(parse_page_range("1-3,5", 5), [0, 1, 2, 4])

    def test_parse_page_range_filters_out_of_bounds(self):
        self.assertEqual(parse_page_range("4,2,7", 4), [3, 1])

    def test_chunked_groups_items_by_size(self):
        self.assertEqual(chunked([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

    def test_chunked_non_positive_size_returns_single_chunk(self):
        self.assertEqual(chunked([1, 2, 3], 0), [[1, 2, 3]])

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

    def test_prepare_latex_for_compile_wraps_decimal_cdots_in_text(self):
        source = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "The value was 1\\cdot87 inches.\n"
            "\\end{document}\n"
        )
        prepared = prepare_latex_for_compile(source, compiler="xelatex")
        self.assertIn("1$\\cdot$87", prepared)


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

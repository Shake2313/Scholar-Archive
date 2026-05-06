"""Regression tests for translate_digitalized_latex per-page fallback."""

import unittest
from unittest.mock import patch

from backend.pipeline import (
    _korean_placeholder_page,
    _translate_chunk,
    translate_digitalized_latex,
)

SIMPLE_PAGE = r"""\documentclass[10pt]{article}
\begin{document}
Hello world page one.
\end{document}
"""

SIMPLE_PAGE_2 = r"""\documentclass[10pt]{article}
\begin{document}
Hello world page two.
\end{document}
"""

KOREAN_BLOCK = r"""%%% BEGIN_KOREAN_LATEX %%%
\documentclass[10pt]{article}
\usepackage{kotex}
\begin{document}
안녕하세요.
\end{document}
%%% END_KOREAN_LATEX %%%
"""

KOREAN_BLOCK_2 = r"""%%% BEGIN_KOREAN_LATEX %%%
\documentclass[10pt]{article}
\usepackage{kotex}
\begin{document}
두 번째 페이지.
\end{document}
%%% END_KOREAN_LATEX %%%
"""


def make_two_page_latex():
    return (
        SIMPLE_PAGE.rstrip()
        + "\n\\newpage\n"
        + r"""\documentclass[10pt]{article}
\begin{document}
Hello world page two.
\end{document}
"""
    )


class TestKoreanPlaceholderPage(unittest.TestCase):
    def test_contains_page_number(self):
        result = _korean_placeholder_page(3, "RECITATION")
        self.assertIn("페이지 3", result)

    def test_contains_reason(self):
        result = _korean_placeholder_page(1, "missing marker")
        self.assertIn("missing marker", result)

    def test_none_page_number(self):
        result = _korean_placeholder_page(None, "error")
        self.assertIn("이 페이지", result)

    def test_is_valid_latex_skeleton(self):
        result = _korean_placeholder_page(5, "test")
        self.assertIn(r"\begin{document}", result)
        self.assertIn(r"\end{document}", result)

    def test_sanitizes_braces_in_reason(self):
        result = _korean_placeholder_page(1, r"failed {reason}")
        self.assertNotIn("{reason}", result)


class TestTranslateChunkMissingMarker(unittest.TestCase):
    def test_raises_value_error_when_marker_missing(self):
        with patch("backend.pipeline.call_text", return_value="no marker here"):
            with self.assertRaises(ValueError):
                _translate_chunk([SIMPLE_PAGE], 1)


class TestTranslateDigitalizedLatexFallback(unittest.TestCase):
    def test_success_returns_three_tuple(self):
        """Happy path: returns (korean_latex, notes, []) with no failures."""
        with patch("backend.pipeline.call_text", return_value=KOREAN_BLOCK):
            result = translate_digitalized_latex(SIMPLE_PAGE, translation_chunk_pages=10)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)
        korean_latex, notes, failed = result
        self.assertIn("안녕하세요", korean_latex)
        self.assertEqual(failed, [])

    def test_chunk_failure_triggers_per_page_retry(self):
        """On chunk failure, each page is retried individually."""
        call_count = 0

        def side_effect(sys_prompt, user_prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("RECITATION")
            return KOREAN_BLOCK

        with patch("backend.pipeline.call_text", side_effect=side_effect):
            korean_latex, notes, failed = translate_digitalized_latex(
                SIMPLE_PAGE, translation_chunk_pages=10
            )
        self.assertEqual(call_count, 2)
        self.assertEqual(failed, [])
        self.assertIn("안녕하세요", korean_latex)

    def test_page_failure_inserts_placeholder(self):
        """When chunk and per-page both fail, a placeholder is inserted."""
        with patch("backend.pipeline.call_text", side_effect=RuntimeError("SAFETY")):
            korean_latex, notes, failed = translate_digitalized_latex(
                SIMPLE_PAGE, translation_chunk_pages=10
            )
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["page_number"], 1)
        self.assertIn("SAFETY", failed[0]["reason"])
        self.assertIn("한국어 번역이 자동 생성되지 못했습니다", korean_latex)

    def test_partial_failure_two_pages(self):
        """Second chunk fails; first succeeds. Result has one placeholder."""
        two_page = make_two_page_latex()
        call_count = 0

        def side_effect(sys_prompt, user_prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return KOREAN_BLOCK
            raise RuntimeError("page 2 blocked")

        with patch("backend.pipeline.call_text", side_effect=side_effect):
            korean_latex, notes, failed = translate_digitalized_latex(
                two_page, translation_chunk_pages=1
            )
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["page_number"], 2)

    def test_page_numbers_passed_to_failed_dict(self):
        """Explicit page_numbers list is reflected in failed_translation_pages."""
        with patch("backend.pipeline.call_text", side_effect=RuntimeError("blocked")):
            _, _, failed = translate_digitalized_latex(
                SIMPLE_PAGE,
                translation_chunk_pages=10,
                page_numbers=[42],
            )
        self.assertEqual(failed[0]["page_number"], 42)

    def test_all_pages_fail_returns_placeholder_content(self):
        """When every page fails, result still contains placeholder content, not empty string."""
        with patch("backend.pipeline.call_text", side_effect=RuntimeError("blocked")):
            korean_latex, notes, failed = translate_digitalized_latex(
                SIMPLE_PAGE, translation_chunk_pages=10
            )
        self.assertGreater(len(failed), 0)
        self.assertIn("한국어 번역이 자동 생성되지 못했습니다", korean_latex)


if __name__ == "__main__":
    unittest.main()

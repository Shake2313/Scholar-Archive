import shutil
import unittest
import uuid
from pathlib import Path

from operations import build_operations_summary, summarize_output_directory


class OperationsSummaryTests(unittest.TestCase):
    def make_workspace_dir(self):
        root = Path(__file__).resolve().parents[1] / "tests_tmp"
        root.mkdir(exist_ok=True)
        path = root / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_summarize_output_directory_marks_publish_ready(self):
        root = self.make_workspace_dir()
        output_dir = root / "demo"
        output_dir.mkdir()
        (output_dir / "demo_quality_report.json").write_text(
            """
            {
              "paper_name": "Demo Paper",
              "total_pages": 3,
              "transcription": {
                "successful_pages": 3,
                "failed_pages": [],
                "partial_output": false
              },
              "digitalized_pdf": {
                "compiled": true
              },
              "korean_pdf": {
                "compiled": true
              }
            }
            """.strip(),
            encoding="utf-8",
        )

        summary = summarize_output_directory(output_dir)

        self.assertEqual(summary["title"], "Demo Paper")
        self.assertEqual(summary["publish_status"], "missing")
        self.assertTrue(summary["publish_ready"])
        self.assertEqual(summary["next_action"], "Publish to Supabase")

    def test_summarize_output_directory_prioritizes_failed_pages(self):
        root = self.make_workspace_dir()
        output_dir = root / "partial"
        output_dir.mkdir()
        (output_dir / "partial_quality_report.json").write_text(
            """
            {
              "paper_name": "Partial Paper",
              "total_pages": 4,
              "transcription": {
                "successful_pages": 3,
                "failed_pages": [4],
                "partial_output": true
              },
              "digitalized_pdf": {
                "compiled": true
              },
              "korean_pdf": {
                "compiled": true
              }
            }
            """.strip(),
            encoding="utf-8",
        )

        summary = summarize_output_directory(output_dir)

        self.assertEqual(summary["failed_pages"], [4])
        self.assertTrue(summary["partial_output"])
        self.assertFalse(summary["publish_ready"])
        self.assertEqual(summary["next_action"], "Retry failed pages")

    def test_build_operations_summary_counts_and_orders_documents(self):
        root = self.make_workspace_dir()

        published_dir = root / "published"
        published_dir.mkdir()
        (published_dir / "published_quality_report.json").write_text(
            """
            {
              "paper_name": "Published Paper",
              "total_pages": 2,
              "transcription": {
                "successful_pages": 2,
                "failed_pages": [],
                "partial_output": false
              },
              "digitalized_pdf": {
                "compiled": true
              },
              "korean_pdf": {
                "compiled": true
              }
            }
            """.strip(),
            encoding="utf-8",
        )
        (published_dir / "published_publish_report.json").write_text(
            """
            {
              "status": "published",
              "slug": "published-paper",
              "published_at": "2026-03-20T18:00:44"
            }
            """.strip(),
            encoding="utf-8",
        )

        failed_dir = root / "failed_publish"
        failed_dir.mkdir()
        (failed_dir / "failed_publish_quality_report.json").write_text(
            """
            {
              "paper_name": "Failed Publish",
              "total_pages": 2,
              "transcription": {
                "successful_pages": 2,
                "failed_pages": [],
                "partial_output": false
              },
              "digitalized_pdf": {
                "compiled": true
              },
              "korean_pdf": {
                "compiled": true
              }
            }
            """.strip(),
            encoding="utf-8",
        )
        (failed_dir / "failed_publish_publish_report.json").write_text(
            """
            {
              "status": "failed",
              "reason": "timeout"
            }
            """.strip(),
            encoding="utf-8",
        )

        summary = build_operations_summary(root)

        self.assertEqual(summary["counts"]["total_outputs"], 2)
        self.assertEqual(summary["counts"]["published_outputs"], 1)
        self.assertEqual(summary["counts"]["publish_failed_outputs"], 1)
        self.assertEqual(summary["documents"][0]["folder_name"], "failed_publish")
        self.assertEqual(summary["documents"][1]["folder_name"], "published")


if __name__ == "__main__":
    unittest.main()

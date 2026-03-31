import shutil
import unittest
import uuid
from datetime import datetime, timedelta
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

    def test_summarize_output_directory_exposes_stage_error_and_runtime_settings(self):
        root = self.make_workspace_dir()
        output_dir = root / "stateful"
        output_dir.mkdir()
        (output_dir / "stateful_quality_report.json").write_text(
            """
            {
              "paper_name": "Stateful Paper",
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
        (output_dir / "stateful_pipeline_state.json").write_text(
            """
            {
              "paper_name": "Stateful Paper",
              "current_stage": "publish",
              "last_successful_stage": "report",
              "last_error": "Supabase DNS timeout",
              "runtime_settings": {
                "api_timeout_sec": 180,
                "api_retry_attempts": 2,
                "latex_compile_timeout_sec": 120
              }
            }
            """.strip(),
            encoding="utf-8",
        )

        summary = summarize_output_directory(output_dir)

        self.assertEqual(summary["current_stage"], "publish")
        self.assertEqual(summary["last_successful_stage"], "report")
        self.assertEqual(summary["last_error"], "Supabase DNS timeout")
        self.assertEqual(summary["api_timeout_sec"], 180)
        self.assertEqual(summary["api_retry_attempts"], 2)
        self.assertEqual(summary["latex_compile_timeout_sec"], 120)

    def test_summarize_output_directory_flags_hung_pipeline_and_exposes_logs(self):
        root = self.make_workspace_dir()
        output_dir = root / "running"
        output_dir.mkdir()
        stdout_log = output_dir / "running_pipeline_stdout.log"
        stderr_log = output_dir / "running_pipeline_stderr.log"
        stdout_log.write_text("step log", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        stale_progress = (datetime.now() - timedelta(minutes=15)).isoformat(timespec="seconds")
        (output_dir / "running_pipeline_state.json").write_text(
            f"""
            {{
              "paper_name": "Running Paper",
              "current_stage": "translation",
              "last_successful_stage": "digitalized_pdf",
              "last_progress_at": "{stale_progress}",
              "last_progress_note": "Translating chunk 1/3.",
              "stdout_log_path": "{stdout_log.as_posix()}",
              "stderr_log_path": "{stderr_log.as_posix()}",
              "runtime_settings": {{
                "api_timeout_sec": 180,
                "api_retry_attempts": 2,
                "latex_compile_timeout_sec": 120
              }}
            }}
            """.strip(),
            encoding="utf-8",
        )

        summary = summarize_output_directory(output_dir)

        self.assertTrue(summary["hung_suspected"])
        self.assertEqual(summary["next_action"], "Inspect hung pipeline")
        self.assertEqual(summary["stdout_log_path"], str(stdout_log))
        self.assertEqual(summary["stderr_log_path"], str(stderr_log))
        self.assertEqual(summary["last_progress_note"], "Translating chunk 1/3.")
        self.assertGreaterEqual(summary["seconds_since_progress"], 900)
        self.assertEqual(summary["hung_threshold_sec"], 600)

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

    def test_summarize_output_directory_prefers_manual_metadata_override_title(self):
        root = self.make_workspace_dir()
        output_dir = root / "override"
        output_dir.mkdir()
        (output_dir / "override_metadata.json").write_text(
            """
            {
              "effective_metadata": {
                "title": "Auto Title"
              }
            }
            """.strip(),
            encoding="utf-8",
        )
        (output_dir / "override_metadata_override.json").write_text(
            """
            {
              "updated_at": "2026-03-31T12:00:00",
              "overrides": {
                "title": "Manual Title",
                "author": "Manual Author"
              }
            }
            """.strip(),
            encoding="utf-8",
        )

        summary = summarize_output_directory(output_dir)

        self.assertEqual(summary["title"], "Manual Title")
        self.assertEqual(summary["metadata_override_fields"], ["author", "title"])

    def test_summarize_output_directory_exposes_metadata_review_summary(self):
        root = self.make_workspace_dir()
        output_dir = root / "metadata_review"
        output_dir.mkdir()
        (output_dir / "metadata_review_metadata.json").write_text(
            """
            {
              "ai_inference": {
                "title": "Probable Title",
                "author": "Likely Author",
                "publication_year": 1912,
                "confidence": {
                  "title": "medium",
                  "author": "high",
                  "publication_year": "low"
                },
                "evidence": {
                  "title": "Title line on first page",
                  "author": "Signed at the end",
                  "publication_year": "Footnote on page 1"
                },
                "status": "ok"
              },
              "effective_metadata": {
                "title": "Probable Title",
                "author": "Likely Author",
                "publication_year": 1912
              },
              "effective_sources": {
                "title": "ai",
                "author": "ai",
                "publication_year": "ai"
              }
            }
            """.strip(),
            encoding="utf-8",
        )

        summary = summarize_output_directory(output_dir)

        self.assertEqual(summary["metadata_ai_status"], "ok")
        self.assertTrue(summary["metadata_review_needed"])
        self.assertEqual(summary["metadata_review_fields"], ["title", "publication_year"])
        self.assertIn("Title=medium", summary["metadata_review_summary"])
        self.assertIn("Publication year=low", summary["metadata_review_summary"])
        rows = {row["field"]: row for row in summary["metadata_review_rows"]}
        self.assertEqual(rows["title"]["ai_evidence"], "Title line on first page")
        self.assertTrue(rows["title"]["review_needed"])
        self.assertFalse(rows["author"]["review_needed"])

    def test_summarize_output_directory_applies_metadata_override_to_review_rows(self):
        root = self.make_workspace_dir()
        output_dir = root / "metadata_override_review"
        output_dir.mkdir()
        (output_dir / "metadata_override_review_metadata.json").write_text(
            """
            {
              "ai_inference": {
                "title": "Probable Title",
                "confidence": {
                  "title": "low"
                },
                "evidence": {
                  "title": "Blurred header"
                },
                "status": "ok"
              },
              "effective_metadata": {
                "title": "Probable Title"
              },
              "effective_sources": {
                "title": "ai"
              }
            }
            """.strip(),
            encoding="utf-8",
        )
        (output_dir / "metadata_override_review_metadata_override.json").write_text(
            """
            {
              "updated_at": "2026-03-31T12:00:00",
              "overrides": {
                "title": "Manual Title"
              }
            }
            """.strip(),
            encoding="utf-8",
        )

        summary = summarize_output_directory(output_dir)

        self.assertFalse(summary["metadata_review_needed"])
        rows = {row["field"]: row for row in summary["metadata_review_rows"]}
        self.assertEqual(rows["title"]["effective_value"], "Manual Title")
        self.assertEqual(rows["title"]["effective_source"], "manual_override")
        self.assertEqual(rows["title"]["manual_override_value"], "Manual Title")
        self.assertFalse(rows["title"]["review_needed"])

    def test_summarize_output_directory_exposes_dns_publish_issue(self):
        root = self.make_workspace_dir()
        output_dir = root / "dns_publish"
        output_dir.mkdir()
        (output_dir / "dns_publish_quality_report.json").write_text(
            """
            {
              "paper_name": "DNS Publish",
              "total_pages": 1,
              "transcription": {
                "successful_pages": 1,
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
        (output_dir / "dns_publish_publish_report.json").write_text(
            """
            {
              "status": "failed",
              "reason": "Could not resolve Supabase host project.supabase.co: Name or service not known",
              "health_check": {
                "status": "dns_failed",
                "reason": "Could not resolve Supabase host project.supabase.co: Name or service not known"
              }
            }
            """.strip(),
            encoding="utf-8",
        )

        summary = summarize_output_directory(output_dir)

        self.assertEqual(summary["publish_issue_type"], "dns")
        self.assertEqual(summary["publish_issue_label"], "DNS")
        self.assertIn("project.supabase.co", summary["publish_issue_detail"])
        self.assertEqual(summary["next_action"], "Fix Supabase connectivity")

    def test_summarize_output_directory_exposes_auth_publish_issue(self):
        root = self.make_workspace_dir()
        output_dir = root / "auth_publish"
        output_dir.mkdir()
        (output_dir / "auth_publish_quality_report.json").write_text(
            """
            {
              "paper_name": "Auth Publish",
              "total_pages": 1,
              "transcription": {
                "successful_pages": 1,
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
        (output_dir / "auth_publish_publish_report.json").write_text(
            """
            {
              "status": "failed",
              "reason": "Supabase API rejected the service key: Supabase GET storage/v1/bucket failed (401): {}",
              "health_check": {
                "status": "auth_failed",
                "reason": "Supabase API rejected the service key: Supabase GET storage/v1/bucket failed (401): {}"
              }
            }
            """.strip(),
            encoding="utf-8",
        )

        summary = summarize_output_directory(output_dir)

        self.assertEqual(summary["publish_issue_type"], "auth")
        self.assertEqual(summary["publish_issue_label"], "Auth")
        self.assertIn("service key", summary["publish_issue_detail"])
        self.assertEqual(summary["next_action"], "Fix Supabase credentials")

    def test_summarize_output_directory_exposes_missing_file_publish_issue(self):
        root = self.make_workspace_dir()
        output_dir = root / "missing_file_publish"
        output_dir.mkdir()
        (output_dir / "missing_file_publish_quality_report.json").write_text(
            """
            {
              "paper_name": "Missing File Publish",
              "total_pages": 1,
              "transcription": {
                "successful_pages": 1,
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
        (output_dir / "missing_file_publish_publish_report.json").write_text(
            """
            {
              "status": "failed",
              "reason": "Missing Korean TeX: C:/tmp/output/missing_file_publish_Korean.tex"
            }
            """.strip(),
            encoding="utf-8",
        )

        summary = summarize_output_directory(output_dir)

        self.assertEqual(summary["publish_issue_type"], "missing_file")
        self.assertEqual(summary["publish_issue_label"], "Missing file")
        self.assertIn("Missing Korean TeX", summary["publish_issue_summary"])
        self.assertEqual(summary["next_action"], "Fix publish inputs")

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
        self.assertEqual(summary["counts"]["metadata_review_outputs"], 0)
        self.assertEqual(summary["documents"][0]["folder_name"], "failed_publish")
        self.assertEqual(summary["documents"][1]["folder_name"], "published")


if __name__ == "__main__":
    unittest.main()

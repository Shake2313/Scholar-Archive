import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from publish import (
    apply_metadata_override,
    build_publish_bundle_from_existing_output,
    collect_publish_queue,
    delete_metadata_override,
    infer_output_name,
    load_metadata_override,
    publish_ready_outputs,
    save_metadata_override,
    write_metadata_override,
)


class ExistingOutputPublishTests(unittest.TestCase):
    def make_workspace_dir(self):
        root = Path(__file__).resolve().parents[1] / "tests_tmp"
        root.mkdir(exist_ok=True)
        path = root / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_build_publish_bundle_from_existing_output_allows_missing_source_pdf(self):
        root = self.make_workspace_dir()
        output_dir = root / "legacy"
        (output_dir / "images").mkdir(parents=True)
        (output_dir / "legacy_digitalized.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nDigital legacy\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "legacy_Korean.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nKorean legacy\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_001.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nPage 1\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_001_structure.json").write_text(
            '{"article_header":{"title_text":"Legacy Title","author_line":"By Legacy Author"},"footnotes":["Printed in 1918"]}',
            encoding="utf-8",
        )
        (output_dir / "images" / "page_001.png").write_bytes(b"png")
        (output_dir / "legacy_pipeline_state.json").write_text(
            '{"requested_pages":[1],"successful_pages":[1]}',
            encoding="utf-8",
        )

        bundle = build_publish_bundle_from_existing_output(
            output_dir=str(output_dir),
            name="legacy",
        )

        self.assertEqual(bundle["document"]["title"], "Legacy Title")
        self.assertIsNone(bundle["document"]["source_pdf_path"])
        self.assertTrue(all(asset["asset_type"] != "source_pdf" for asset in bundle["assets"]))

    def test_infer_output_name_uses_report_prefix(self):
        root = self.make_workspace_dir()
        output_dir = root / "ready"
        output_dir.mkdir()
        (output_dir / "sample_quality_report.json").write_text("{}", encoding="utf-8")

        self.assertEqual(infer_output_name(output_dir), "sample")

    def test_save_metadata_override_round_trips_normalized_values(self):
        root = self.make_workspace_dir()
        output_dir = root / "ready"
        output_dir.mkdir()

        save_metadata_override(
            output_dir,
            "sample",
            {
                "title": " Corrected Title ",
                "publication_year": "1918",
                "doi": "",
            },
        )

        self.assertEqual(
            load_metadata_override(output_dir, "sample"),
            {
                "title": "Corrected Title",
                "publication_year": 1918,
            },
        )
        self.assertEqual(
            apply_metadata_override({"author": "Legacy Author"}, {"title": "Corrected Title"}),
            {"author": "Legacy Author", "title": "Corrected Title"},
        )

    def test_write_metadata_override_replaces_existing_values_and_delete_removes_file(self):
        root = self.make_workspace_dir()
        output_dir = root / "ready"
        output_dir.mkdir()

        save_metadata_override(
            output_dir,
            "sample",
            {
                "title": "Corrected Title",
                "author": "Legacy Author",
            },
        )
        write_metadata_override(
            output_dir,
            "sample",
            {
                "title": "Manual Title",
            },
        )

        self.assertEqual(
            load_metadata_override(output_dir, "sample"),
            {"title": "Manual Title"},
        )
        self.assertIsNotNone(delete_metadata_override(output_dir, "sample"))
        self.assertEqual(load_metadata_override(output_dir, "sample"), {})

    def test_build_publish_bundle_from_existing_output_applies_manual_override(self):
        root = self.make_workspace_dir()
        output_dir = root / "legacy"
        (output_dir / "images").mkdir(parents=True)
        (output_dir / "legacy_digitalized.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nDigital legacy\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "legacy_Korean.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nKorean legacy\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_001.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nPage 1\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_001_structure.json").write_text(
            '{"article_header":{"title_text":"Legacy Title","author_line":"By Legacy Author"},"footnotes":["Printed in 1918"]}',
            encoding="utf-8",
        )
        (output_dir / "images" / "page_001.png").write_bytes(b"png")
        (output_dir / "legacy_pipeline_state.json").write_text(
            '{"requested_pages":[1],"successful_pages":[1]}',
            encoding="utf-8",
        )
        save_metadata_override(
            output_dir,
            "legacy",
            {
                "title": "Corrected Legacy Title",
                "author": "Corrected Author",
                "publication_year": 1919,
            },
        )

        bundle = build_publish_bundle_from_existing_output(
            output_dir=str(output_dir),
            name="legacy",
        )

        self.assertEqual(bundle["document"]["title"], "Corrected Legacy Title")
        self.assertEqual(bundle["document"]["author_display"], "Corrected Author")
        self.assertEqual(bundle["document"]["publication_year"], 1919)
        self.assertEqual(bundle["snapshot"]["manual_override"]["title"], "Corrected Legacy Title")

    def test_collect_publish_queue_keeps_ready_outputs_and_skips_duplicate_slugs(self):
        root = self.make_workspace_dir()

        first = root / "first_ready"
        first.mkdir()
        (first / "first_quality_report.json").write_text(
            """
            {
              "paper_name": "Alpha Paper",
              "total_pages": 1,
              "transcription": {"successful_pages": 1, "failed_pages": [], "partial_output": false},
              "digitalized_pdf": {"compiled": true},
              "korean_pdf": {"compiled": true}
            }
            """.strip(),
            encoding="utf-8",
        )

        duplicate = root / "duplicate_ready"
        duplicate.mkdir()
        (duplicate / "duplicate_quality_report.json").write_text(
            """
            {
              "paper_name": "Alpha Paper",
              "total_pages": 1,
              "transcription": {"successful_pages": 1, "failed_pages": [], "partial_output": false},
              "digitalized_pdf": {"compiled": true},
              "korean_pdf": {"compiled": true}
            }
            """.strip(),
            encoding="utf-8",
        )

        partial = root / "partial"
        partial.mkdir()
        (partial / "partial_quality_report.json").write_text(
            """
            {
              "paper_name": "Partial Paper",
              "total_pages": 1,
              "transcription": {"successful_pages": 0, "failed_pages": [1], "partial_output": true},
              "digitalized_pdf": {"compiled": true},
              "korean_pdf": {"compiled": true}
            }
            """.strip(),
            encoding="utf-8",
        )

        published = root / "published"
        published.mkdir()
        (published / "published_quality_report.json").write_text(
            """
            {
              "paper_name": "Published Paper",
              "total_pages": 1,
              "transcription": {"successful_pages": 1, "failed_pages": [], "partial_output": false},
              "digitalized_pdf": {"compiled": true},
              "korean_pdf": {"compiled": true}
            }
            """.strip(),
            encoding="utf-8",
        )
        (published / "published_publish_report.json").write_text(
            "{\"status\": \"published\", \"slug\": \"published-paper\"}",
            encoding="utf-8",
        )

        queue = collect_publish_queue(root)

        self.assertEqual([item["folder_name"] for item in queue["queued"]], ["duplicate_ready"])
        self.assertEqual(queue["queued"][0]["name"], "duplicate")
        self.assertEqual(queue["queued"][0]["slug"], "alpha-paper")
        self.assertEqual(len(queue["skipped"]), 1)
        self.assertEqual(queue["skipped"][0]["status"], "skipped_duplicate_slug")

    def test_publish_ready_outputs_processes_queue_in_priority_order(self):
        root = self.make_workspace_dir()

        first = root / "a_ready"
        first.mkdir()
        (first / "alpha_quality_report.json").write_text(
            """
            {
              "paper_name": "First Paper",
              "total_pages": 1,
              "transcription": {"successful_pages": 1, "failed_pages": [], "partial_output": false},
              "digitalized_pdf": {"compiled": true},
              "korean_pdf": {"compiled": true}
            }
            """.strip(),
            encoding="utf-8",
        )

        second = root / "b_ready"
        second.mkdir()
        (second / "beta_quality_report.json").write_text(
            """
            {
              "paper_name": "Second Paper",
              "total_pages": 1,
              "transcription": {"successful_pages": 1, "failed_pages": [], "partial_output": false},
              "digitalized_pdf": {"compiled": true},
              "korean_pdf": {"compiled": true}
            }
            """.strip(),
            encoding="utf-8",
        )

        def fake_publish_existing_output(*, output_dir, name, dry_run, slug_conflict_policy):
            return {
                "output_dir": str(Path(output_dir).resolve()),
                "name": name,
                "slug": f"{name}-slug",
                "report": {
                    "status": "dry_run" if dry_run else "published",
                    "reason": None,
                    "published_at": None,
                    "slug_conflict_policy": "skip",
                    "overwrote_existing": False,
                },
                "report_path": str(Path(output_dir) / f"{name}_publish_report.json"),
            }

        with patch("publish.publish_existing_output", side_effect=fake_publish_existing_output) as mocked:
            batch = publish_ready_outputs(root, dry_run=True, slug_conflict_policy="skip")

        self.assertEqual(
            [
                (
                    call.kwargs["output_dir"],
                    call.kwargs["name"],
                    call.kwargs["slug_conflict_policy"],
                )
                for call in mocked.call_args_list
            ],
            [
                (str(first.resolve()), "alpha", "skip"),
                (str(second.resolve()), "beta", "skip"),
            ],
        )
        self.assertEqual(batch["counts"]["queued_outputs"], 2)
        self.assertEqual(batch["counts"]["dry_run_outputs"], 2)
        self.assertEqual(batch["slug_conflict_policy"], "skip")
        self.assertEqual([item["folder_name"] for item in batch["results"]], ["a_ready", "b_ready"])


if __name__ == "__main__":
    unittest.main()

import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend.publish_batch import (
    collect_publish_queue,
    publish_existing_output,
    publish_ready_outputs,
)


class PublishBatchTests(unittest.TestCase):
    def make_workspace_dir(self):
        root = Path(__file__).resolve().parent / ".tmp"
        root.mkdir(exist_ok=True)
        path = root / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def write_ready_report(self, output_dir: Path, name: str, paper_name: str):
        output_dir.mkdir()
        (output_dir / f"{name}_quality_report.json").write_text(
            json.dumps(
                {
                    "paper_name": paper_name,
                    "total_pages": 1,
                    "transcription": {
                        "successful_pages": 1,
                        "failed_pages": [],
                        "partial_output": False,
                    },
                    "digitalized_pdf": {"compiled": True},
                    "korean_pdf": {"compiled": True},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def test_publish_existing_output_dry_run_saves_report(self):
        output_dir = self.make_workspace_dir()
        bundle = {
            "document": {"slug": "demo-paper"},
            "storage_bucket": "scholar-archive",
            "storage_root": "documents/demo-paper",
            "assets": [{"storage_path": "documents/demo-paper/source.pdf"}],
            "pages": [{"page_number": 1}],
        }

        with patch(
            "backend.publish_batch.build_publish_bundle_from_existing_output",
            return_value=bundle,
        ):
            result = publish_existing_output(
                output_dir=str(output_dir),
                name="demo",
                dry_run=True,
                slug_conflict_policy="skip",
            )

        report_path = Path(result["report_path"])
        saved_report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_report["status"], "dry_run")
        self.assertEqual(saved_report["slug"], "demo-paper")
        self.assertEqual(saved_report["slug_conflict_policy"], "skip")
        self.assertEqual(result["slug"], "demo-paper")

    def test_collect_publish_queue_keeps_ready_outputs_and_skips_duplicate_slugs(self):
        root = self.make_workspace_dir()

        self.write_ready_report(root / "first_ready", "first", "Alpha Paper")
        self.write_ready_report(root / "duplicate_ready", "duplicate", "Alpha Paper")

        partial = root / "partial"
        partial.mkdir()
        (partial / "partial_quality_report.json").write_text(
            json.dumps(
                {
                    "paper_name": "Partial Paper",
                    "total_pages": 1,
                    "transcription": {
                        "successful_pages": 0,
                        "failed_pages": [1],
                        "partial_output": True,
                    },
                    "digitalized_pdf": {"compiled": True},
                    "korean_pdf": {"compiled": True},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        published = root / "published"
        self.write_ready_report(published, "published", "Published Paper")
        (published / "published_publish_report.json").write_text(
            json.dumps({"status": "published", "slug": "published-paper"}),
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
        second = root / "b_ready"
        self.write_ready_report(first, "alpha", "First Paper")
        self.write_ready_report(second, "beta", "Second Paper")

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

        with patch(
            "backend.publish_batch.publish_existing_output",
            side_effect=fake_publish_existing_output,
        ) as mocked:
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

    def test_publish_ready_outputs_writes_failed_report_when_publish_raises(self):
        root = self.make_workspace_dir()
        ready = root / "ready"
        self.write_ready_report(ready, "sample", "Sample Paper")

        with patch(
            "backend.publish_batch.publish_existing_output",
            side_effect=RuntimeError("network timeout"),
        ):
            batch = publish_ready_outputs(root, slug_conflict_policy="skip")

        report_path = ready / "sample_publish_report.json"
        saved_report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(batch["counts"]["failed_outputs"], 1)
        self.assertEqual(batch["results"][0]["status"], "failed")
        self.assertEqual(saved_report["status"], "failed")
        self.assertEqual(saved_report["slug_conflict_policy"], "skip")
        self.assertEqual(saved_report["reason"], "network timeout")


if __name__ == "__main__":
    unittest.main()

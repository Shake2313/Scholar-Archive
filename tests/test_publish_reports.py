import json
import shutil
import unittest
import uuid
from pathlib import Path

from backend.publish_reports import (
    build_disabled_publish_report,
    build_dry_run_publish_report,
    build_failed_publish_report,
    build_publish_batch_counts,
    publish_report_path,
    save_publish_report,
)


class PublishReportTests(unittest.TestCase):
    def make_workspace_dir(self):
        root = Path(__file__).resolve().parent / ".tmp"
        root.mkdir(exist_ok=True)
        path = root / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_build_dry_run_publish_report_includes_policy_when_requested(self):
        bundle = {
            "document": {"slug": "demo-paper"},
            "storage_bucket": "scholar-archive",
            "storage_root": "documents/demo-paper",
            "assets": [{}, {}],
            "pages": [{}],
        }

        report = build_dry_run_publish_report(bundle, slug_conflict_policy="skip")

        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(report["slug"], "demo-paper")
        self.assertEqual(report["uploaded_assets"], 2)
        self.assertEqual(report["published_pages"], 1)
        self.assertEqual(report["slug_conflict_policy"], "skip")

    def test_build_disabled_and_failed_publish_reports_share_shape(self):
        disabled = build_disabled_publish_report()
        failed = build_failed_publish_report(
            slug="demo-paper",
            reason="missing files",
            slug_conflict_policy="overwrite",
            health_check={"status": "dns_failed"},
        )

        self.assertEqual(disabled["status"], "disabled")
        self.assertIsNone(disabled["slug"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["slug"], "demo-paper")
        self.assertEqual(failed["slug_conflict_policy"], "overwrite")
        self.assertEqual(failed["health_check"]["status"], "dns_failed")

    def test_save_publish_report_round_trips_json(self):
        output_dir = self.make_workspace_dir()
        report = {"status": "published", "slug": "demo-paper"}

        path = save_publish_report(output_dir, "demo", report)
        saved = json.loads(Path(path).read_text(encoding="utf-8"))

        self.assertEqual(path, publish_report_path(output_dir, "demo"))
        self.assertEqual(saved, report)

    def test_build_publish_batch_counts_summarizes_statuses(self):
        counts = build_publish_batch_counts(
            queued=[{"name": "a"}, {"name": "b"}],
            skipped=[{"name": "c"}],
            results=[
                {"status": "published"},
                {"status": "failed"},
                {"status": "dry_run"},
            ],
        )

        self.assertEqual(
            counts,
            {
                "queued_outputs": 2,
                "skipped_outputs": 1,
                "published_outputs": 1,
                "failed_outputs": 1,
                "dry_run_outputs": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()

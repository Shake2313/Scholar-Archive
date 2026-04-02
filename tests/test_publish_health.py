import socket
import unittest
from unittest.mock import patch

from backend.publish import (
    check_supabase_publish_health,
    normalize_slug_conflict_policy,
    publish_bundle_to_supabase,
)


class PublishHealthTests(unittest.TestCase):
    def test_normalize_slug_conflict_policy_rejects_unknown_value(self):
        with self.assertRaises(ValueError):
            normalize_slug_conflict_policy("replace")

    def test_check_supabase_publish_health_reports_missing_credentials(self):
        with patch("backend.publish.get_supabase_url", return_value=None), patch(
            "backend.publish.get_supabase_service_key", return_value=None
        ):
            report = check_supabase_publish_health()

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "missing_credentials")
        self.assertIn("Supabase credentials are missing", report["reason"])

    def test_check_supabase_publish_health_reports_dns_failure(self):
        with patch(
            "backend.publish.socket.getaddrinfo",
            side_effect=socket.gaierror(-2, "Name or service not known"),
        ):
            report = check_supabase_publish_health(
                "https://demo.supabase.co",
                "service-role-key",
            )

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "dns_failed")
        self.assertFalse(report["dns_ok"])
        self.assertFalse(report["api_ok"])
        self.assertIn("Could not resolve Supabase host demo.supabase.co", report["reason"])

    def test_check_supabase_publish_health_reports_auth_failure(self):
        with patch("backend.publish.socket.getaddrinfo", return_value=[object()]), patch(
            "backend.publish._supabase_request",
            side_effect=RuntimeError("Supabase GET storage/v1/bucket failed (401): invalid JWT"),
        ):
            report = check_supabase_publish_health(
                "https://demo.supabase.co",
                "bad-key",
            )

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "auth_failed")
        self.assertTrue(report["dns_ok"])
        self.assertTrue(report["api_ok"])
        self.assertIn("rejected the service key", report["reason"])

    def test_publish_bundle_to_supabase_stops_after_failed_health_check(self):
        bundle = {
            "document": {"slug": "demo-paper"},
            "storage_bucket": "scholar-archive",
            "storage_root": "documents/demo-paper",
            "assets": [],
            "pages": [],
            "snapshot": {},
        }
        health_check = {
            "ok": False,
            "status": "dns_failed",
            "reason": "Could not resolve Supabase host demo.supabase.co: no such host",
        }
        with patch("backend.publish.check_supabase_publish_health", return_value=health_check), patch(
            "backend.publish._ensure_storage_bucket"
        ) as ensure_bucket:
            report = publish_bundle_to_supabase(bundle)

        ensure_bucket.assert_not_called()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["slug"], "demo-paper")
        self.assertEqual(report["health_check"], health_check)

    def test_publish_bundle_to_supabase_skips_existing_slug_when_policy_is_skip(self):
        bundle = {
            "document": {"slug": "demo-paper"},
            "storage_bucket": "scholar-archive",
            "storage_root": "documents/demo-paper",
            "assets": [],
            "pages": [],
            "snapshot": {},
        }
        health_check = {"ok": True, "status": "ok", "reason": None}
        existing_document = {"id": 12, "slug": "demo-paper", "title": "Existing Paper"}
        with patch("backend.publish.check_supabase_publish_health", return_value=health_check), patch(
            "backend.publish._fetch_existing_document_by_slug",
            return_value=existing_document,
        ), patch("backend.publish._ensure_storage_bucket") as ensure_bucket:
            report = publish_bundle_to_supabase(bundle, slug_conflict_policy="skip")

        ensure_bucket.assert_not_called()
        self.assertEqual(report["status"], "skipped")
        self.assertEqual(report["slug_conflict_policy"], "skip")
        self.assertFalse(report["overwrote_existing"])
        self.assertEqual(report["existing_document_id"], 12)

    def test_publish_bundle_to_supabase_overwrites_existing_slug_when_policy_is_overwrite(self):
        bundle = {
            "document": {"slug": "demo-paper"},
            "storage_bucket": "scholar-archive",
            "storage_root": "documents/demo-paper",
            "assets": [],
            "pages": [],
            "snapshot": {},
            "author": None,
        }
        health_check = {"ok": True, "status": "ok", "reason": None}
        existing_document = {"id": 12, "slug": "demo-paper", "title": "Existing Paper"}
        with patch("backend.publish.check_supabase_publish_health", return_value=health_check), patch(
            "backend.publish._fetch_existing_document_by_slug",
            return_value=existing_document,
        ), patch("backend.publish._ensure_storage_bucket"), patch(
            "backend.publish._upsert_rows",
            side_effect=[[{"id": 12, "slug": "demo-paper"}], [], [], []],
        ) as upsert_rows, patch("backend.publish._delete_rows"):
            report = publish_bundle_to_supabase(bundle, slug_conflict_policy="overwrite")

        self.assertEqual(report["status"], "published")
        self.assertEqual(report["slug_conflict_policy"], "overwrite")
        self.assertTrue(report["overwrote_existing"])
        self.assertEqual(report["existing_document_id"], 12)
        self.assertIn("Overwrote existing document", report["reason"])
        self.assertGreaterEqual(upsert_rows.call_count, 2)


if __name__ == "__main__":
    unittest.main()

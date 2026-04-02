"""
Helpers for building and saving publish report payloads.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def publish_report_path(output_dir: str | Path, name: str) -> str:
    return os.path.join(output_dir, f"{name}_publish_report.json")


def save_publish_report(output_dir: str | Path, name: str, report: dict[str, Any]) -> str:
    path = publish_report_path(output_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path


def build_dry_run_publish_report(
    bundle: dict[str, Any],
    *,
    slug_conflict_policy: str | None = None,
) -> dict[str, Any]:
    report = {
        "status": "dry_run",
        "reason": None,
        "slug": bundle["document"]["slug"],
        "storage_bucket": bundle["storage_bucket"],
        "storage_root": bundle["storage_root"],
        "uploaded_assets": len(bundle["assets"]),
        "published_pages": len(bundle["pages"]),
        "published_at": None,
    }
    if slug_conflict_policy is not None:
        report["slug_conflict_policy"] = slug_conflict_policy
    return report


def build_disabled_publish_report(
    *,
    reason: str = "Publishing disabled by configuration.",
) -> dict[str, Any]:
    return {
        "status": "disabled",
        "reason": reason,
        "slug": None,
        "published_at": None,
    }


def build_failed_publish_report(
    *,
    slug: str | None,
    reason: str,
    slug_conflict_policy: str | None = None,
    health_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "failed",
        "reason": reason,
        "slug": slug,
        "published_at": None,
    }
    if slug_conflict_policy is not None:
        report["slug_conflict_policy"] = slug_conflict_policy
    if health_check is not None:
        report["health_check"] = health_check
    return report


def build_publish_batch_counts(
    *,
    queued: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "queued_outputs": len(queued),
        "skipped_outputs": len(skipped),
        "published_outputs": sum(1 for item in results if item["status"] == "published"),
        "failed_outputs": sum(1 for item in results if item["status"] == "failed"),
        "dry_run_outputs": sum(1 for item in results if item["status"] == "dry_run"),
    }

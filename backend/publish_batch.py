"""
Batch orchestration helpers for publishing existing output directories.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.publish import (
    DEFAULT_SLUG_CONFLICT_POLICY,
    build_publish_bundle_from_existing_output,
    infer_output_name,
    normalize_slug_conflict_policy,
    publish_bundle_to_supabase,
    slugify,
)
from backend.publish_reports import (
    build_dry_run_publish_report,
    build_failed_publish_report,
    build_publish_batch_counts,
    save_publish_report,
)


def publish_existing_output(
    *,
    output_dir: str,
    name: str,
    dry_run: bool = False,
    slug_conflict_policy: str = DEFAULT_SLUG_CONFLICT_POLICY,
) -> dict[str, Any]:
    slug_conflict_policy = normalize_slug_conflict_policy(slug_conflict_policy)
    bundle = build_publish_bundle_from_existing_output(
        output_dir=output_dir,
        name=name,
    )
    report = (
        build_dry_run_publish_report(
            bundle,
            slug_conflict_policy=slug_conflict_policy,
        )
        if dry_run
        else publish_bundle_to_supabase(
            bundle,
            slug_conflict_policy=slug_conflict_policy,
        )
    )
    report_path = save_publish_report(output_dir, name, report)
    return {
        "output_dir": str(Path(output_dir).resolve()),
        "name": name,
        "slug": report.get("slug") or bundle["document"]["slug"],
        "report": report,
        "report_path": report_path,
    }


def _queue_entry_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    output_dir = summary["path"]
    name = infer_output_name(output_dir)
    return {
        "path": output_dir,
        "folder_name": summary["folder_name"],
        "name": name,
        "slug": slugify(summary.get("title") or name),
        "title": summary.get("title"),
        "priority_rank": summary.get("priority_rank"),
        "updated_at": summary.get("updated_at"),
    }


def collect_publish_queue(
    output_root: str | Path,
    *,
    limit: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    from backend.operations import collect_output_summaries

    queue: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_slugs: dict[str, dict[str, Any]] = {}
    for summary in collect_output_summaries(output_root):
        if not summary.get("publish_ready"):
            continue
        try:
            entry = _queue_entry_from_summary(summary)
        except Exception as exc:
            skipped.append(
                {
                    "path": summary["path"],
                    "folder_name": summary["folder_name"],
                    "status": "skipped_unresolved_name",
                    "reason": str(exc).strip() or exc.__class__.__name__,
                }
            )
            continue
        slug = entry["slug"]
        if slug in seen_slugs:
            skipped.append(
                {
                    **entry,
                    "status": "skipped_duplicate_slug",
                    "reason": (
                        f"Slug '{slug}' is already queued for "
                        f"{seen_slugs[slug]['folder_name']}."
                    ),
                }
            )
            continue
        queue.append(entry)
        seen_slugs[slug] = entry
        if limit is not None and limit > 0 and len(queue) >= limit:
            break
    return {"queued": queue, "skipped": skipped}


def _result_from_outcome(entry: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    report = outcome["report"]
    return {
        **entry,
        "status": report["status"],
        "reason": report.get("reason"),
        "report_path": outcome["report_path"],
        "published_at": report.get("published_at"),
        "slug_conflict_policy": report.get("slug_conflict_policy"),
        "overwrote_existing": report.get("overwrote_existing"),
    }


def publish_ready_outputs(
    output_root: str | Path,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    slug_conflict_policy: str = DEFAULT_SLUG_CONFLICT_POLICY,
) -> dict[str, Any]:
    slug_conflict_policy = normalize_slug_conflict_policy(slug_conflict_policy)
    queue_info = collect_publish_queue(output_root, limit=limit)
    results: list[dict[str, Any]] = []
    for entry in queue_info["queued"]:
        try:
            outcome = publish_existing_output(
                output_dir=entry["path"],
                name=entry["name"],
                dry_run=dry_run,
                slug_conflict_policy=slug_conflict_policy,
            )
            results.append(_result_from_outcome(entry, outcome))
        except Exception as exc:
            failed_report = build_failed_publish_report(
                slug=entry["slug"],
                reason=str(exc).strip() or exc.__class__.__name__,
                slug_conflict_policy=slug_conflict_policy,
            )
            report_path = save_publish_report(entry["path"], entry["name"], failed_report)
            results.append(
                {
                    **entry,
                    "status": "failed",
                    "reason": failed_report["reason"],
                    "report_path": report_path,
                    "published_at": None,
                    "slug_conflict_policy": slug_conflict_policy,
                    "overwrote_existing": False,
                }
            )
    return {
        "output_root": str(Path(output_root).resolve()),
        "queued": queue_info["queued"],
        "skipped": queue_info["skipped"],
        "results": results,
        "slug_conflict_policy": slug_conflict_policy,
        "counts": build_publish_batch_counts(
            queued=queue_info["queued"],
            skipped=queue_info["skipped"],
            results=results,
        ),
    }

"""
Helpers for summarizing pipeline outputs for operations workflows.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _first_report(output_path: Path, pattern: str) -> tuple[Path | None, dict[str, Any] | None]:
    matches = sorted(output_path.glob(pattern))
    if not matches:
        return None, None
    report_path = matches[0]
    return report_path, _read_json(report_path)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _coerce_page_numbers(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    page_numbers: list[int] = []
    for value in values:
        page_number = _coerce_int(value)
        if page_number is not None and page_number > 0:
            page_numbers.append(page_number)
    return sorted(set(page_numbers))


def _extract_failed_pages(
    quality_report: dict[str, Any] | None,
    pipeline_state: dict[str, Any] | None,
) -> list[int]:
    report_failed = _coerce_page_numbers((quality_report or {}).get("transcription", {}).get("failed_pages"))
    state_failed = _coerce_page_numbers((pipeline_state or {}).get("failed_pages"))
    return sorted(set(report_failed + state_failed))


def _infer_title(
    output_path: Path,
    quality_report: dict[str, Any] | None,
    metadata_report: dict[str, Any] | None,
    pipeline_state: dict[str, Any] | None,
) -> str:
    effective_metadata = (metadata_report or {}).get("effective_metadata", {})
    title = effective_metadata.get("title")
    if title:
        return str(title)
    paper_name = (quality_report or {}).get("paper_name") or (pipeline_state or {}).get("paper_name")
    if paper_name:
        return str(paper_name)
    return output_path.name


def _reported_pdf_compiled(
    quality_report: dict[str, Any] | None,
    key: str,
    pdf_exists: bool,
    error_exists: bool,
) -> bool:
    compiled = (quality_report or {}).get(key, {}).get("compiled")
    if isinstance(compiled, bool):
        return compiled and not error_exists
    return pdf_exists and not error_exists


def _last_updated_at(paths: list[Path | None]) -> str | None:
    existing = [path for path in paths if path is not None and path.exists()]
    if not existing:
        return None
    latest = max(existing, key=lambda path: path.stat().st_mtime)
    return datetime.fromtimestamp(latest.stat().st_mtime).isoformat(timespec="seconds")


def _next_action(summary: dict[str, Any]) -> str:
    if summary["failed_pages"]:
        return "Retry failed pages"
    if not summary["has_quality_report"]:
        return "Run pipeline"
    if not summary["digitalized_compiled"] or not summary["korean_compiled"]:
        return "Fix PDF compilation"
    if summary["publish_status"] == "failed":
        return "Retry publish"
    if summary["publish_status"] != "published":
        return "Publish to Supabase"
    return "Published"


def _priority_rank(summary: dict[str, Any]) -> int:
    if summary["failed_pages"]:
        return 0
    if not summary["has_quality_report"]:
        return 1
    if not summary["digitalized_compiled"] or not summary["korean_compiled"]:
        return 2
    if summary["publish_status"] == "failed":
        return 3
    if summary["publish_status"] != "published":
        return 4
    return 5


def summarize_output_directory(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    if not output_path.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {output_path}")

    quality_report_path, quality_report = _first_report(output_path, "*_quality_report.json")
    publish_report_path, publish_report = _first_report(output_path, "*_publish_report.json")
    pipeline_state_path, pipeline_state = _first_report(output_path, "*_pipeline_state.json")
    metadata_report_path, metadata_report = _first_report(output_path, "*_metadata.json")

    failed_pages = _extract_failed_pages(quality_report, pipeline_state)
    requested_pages = _coerce_page_numbers((pipeline_state or {}).get("requested_pages"))
    successful_pages = _coerce_page_numbers((pipeline_state or {}).get("successful_pages"))
    successful_page_count = _coerce_int((quality_report or {}).get("transcription", {}).get("successful_pages"))
    if successful_page_count is None:
        successful_page_count = len(successful_pages) or None

    total_pages = _coerce_int((quality_report or {}).get("total_pages"))
    if total_pages is None and requested_pages:
        total_pages = len(requested_pages)
    if total_pages is None and successful_page_count is not None:
        total_pages = successful_page_count + len(failed_pages)

    digitalized_pdf_exists = any(output_path.glob("*_digitalized.pdf"))
    korean_pdf_exists = any(output_path.glob("*_Korean.pdf"))
    digitalized_error_exists = any(output_path.glob("*_digitalized_error.log"))
    korean_error_exists = any(output_path.glob("*_Korean_error.log"))

    publish_status = str((publish_report or {}).get("status") or "missing")
    publish_reason = (publish_report or {}).get("reason")
    partial_output = bool((quality_report or {}).get("transcription", {}).get("partial_output")) or bool(failed_pages)

    summary = {
        "folder_name": output_path.name,
        "path": str(output_path.resolve()),
        "title": _infer_title(output_path, quality_report, metadata_report, pipeline_state),
        "has_quality_report": quality_report_path is not None,
        "has_publish_report": publish_report_path is not None,
        "quality_report_path": str(quality_report_path.resolve()) if quality_report_path else None,
        "publish_report_path": str(publish_report_path.resolve()) if publish_report_path else None,
        "pipeline_state_path": str(pipeline_state_path.resolve()) if pipeline_state_path else None,
        "metadata_report_path": str(metadata_report_path.resolve()) if metadata_report_path else None,
        "total_pages": total_pages,
        "successful_pages": successful_page_count,
        "failed_pages": failed_pages,
        "partial_output": partial_output,
        "digitalized_compiled": _reported_pdf_compiled(
            quality_report,
            "digitalized_pdf",
            digitalized_pdf_exists,
            digitalized_error_exists,
        ),
        "korean_compiled": _reported_pdf_compiled(
            quality_report,
            "korean_pdf",
            korean_pdf_exists,
            korean_error_exists,
        ),
        "publish_status": publish_status,
        "publish_reason": str(publish_reason) if publish_reason else None,
        "published_at": (publish_report or {}).get("published_at"),
        "slug": (publish_report or {}).get("slug"),
        "updated_at": _last_updated_at(
            [quality_report_path, publish_report_path, pipeline_state_path, metadata_report_path]
        ),
    }
    summary["publish_ready"] = (
        summary["has_quality_report"]
        and summary["digitalized_compiled"]
        and summary["korean_compiled"]
        and not summary["failed_pages"]
        and summary["publish_status"] != "published"
    )
    summary["next_action"] = _next_action(summary)
    summary["priority_rank"] = _priority_rank(summary)
    return summary


def collect_output_summaries(output_root: str | Path) -> list[dict[str, Any]]:
    root = Path(output_root)
    if not root.exists():
        return []
    summaries = [summarize_output_directory(path) for path in sorted(root.iterdir()) if path.is_dir()]
    return sorted(summaries, key=lambda item: (item["priority_rank"], item["folder_name"].lower()))


def build_operations_summary(output_root: str | Path) -> dict[str, Any]:
    root = Path(output_root)
    documents = collect_output_summaries(root)
    return {
        "output_root": str(root.resolve()),
        "documents": documents,
        "counts": {
            "total_outputs": len(documents),
            "published_outputs": sum(1 for item in documents if item["publish_status"] == "published"),
            "ready_to_publish_outputs": sum(1 for item in documents if item["publish_ready"]),
            "publish_failed_outputs": sum(1 for item in documents if item["publish_status"] == "failed"),
            "partial_outputs": sum(1 for item in documents if item["partial_output"]),
            "missing_quality_reports": sum(1 for item in documents if not item["has_quality_report"]),
        },
    }

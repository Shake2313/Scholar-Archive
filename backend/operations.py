"""
Helpers for summarizing pipeline outputs for operations workflows.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

METADATA_FIELDS = (
    "title",
    "author",
    "publication_year",
    "death_year",
    "journal_or_book",
    "volume",
    "issue",
    "pages",
    "language",
    "doi",
)
METADATA_FIELD_LABELS = {
    "title": "Title",
    "author": "Author",
    "publication_year": "Publication year",
    "death_year": "Death year",
    "journal_or_book": "Journal or book",
    "volume": "Volume",
    "issue": "Issue",
    "pages": "Pages",
    "language": "Language",
    "doi": "DOI",
}


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


def _load_metadata_override(output_path: Path) -> tuple[Path | None, dict[str, Any]]:
    matches = sorted(output_path.glob("*_metadata_override.json"))
    if not matches:
        return None, {}
    path = matches[0]
    data = _read_json(path) or {}
    payload = data.get("overrides") if isinstance(data.get("overrides"), dict) else data
    normalized: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return path, normalized
    for field, value in payload.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            normalized[field] = value
    return path, normalized


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


def _coerce_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _hung_threshold_seconds(runtime_settings: dict[str, Any]) -> int:
    api_timeout_sec = max(_coerce_int(runtime_settings.get("api_timeout_sec")) or 0, 0)
    api_retry_attempts = max(_coerce_int(runtime_settings.get("api_retry_attempts")) or 0, 0)
    latex_compile_timeout_sec = max(
        _coerce_int(runtime_settings.get("latex_compile_timeout_sec")) or 0,
        0,
    )
    api_budget_sec = api_timeout_sec * (api_retry_attempts + 1)
    return max(api_budget_sec, latex_compile_timeout_sec, 300) + 60


def _progress_health(
    current_stage: Any,
    last_progress_at: Any,
    runtime_settings: dict[str, Any],
) -> tuple[int | None, int, bool]:
    threshold_sec = _hung_threshold_seconds(runtime_settings)
    progress_dt = _coerce_datetime(last_progress_at)
    if progress_dt is None:
        return None, threshold_sec, False
    seconds_since_progress = max(0, int((datetime.now() - progress_dt).total_seconds()))
    is_active = bool(current_stage) and str(current_stage) != "complete"
    return (
        seconds_since_progress,
        threshold_sec,
        is_active and seconds_since_progress > threshold_sec,
    )


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
    metadata_override: dict[str, Any] | None,
) -> str:
    override_title = (metadata_override or {}).get("title")
    if override_title:
        return str(override_title)
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


def _normalize_path_string(value: Any) -> str | None:
    if not value:
        return None
    try:
        return str(Path(str(value)).resolve())
    except Exception:
        return str(value)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_metadata_confidence(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"high", "medium", "low", "none"} else "none"


def _metadata_review_from_report(
    metadata_report: dict[str, Any] | None,
    metadata_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = metadata_report if isinstance(metadata_report, dict) else {}
    ai_metadata = report.get("ai_inference") if isinstance(report.get("ai_inference"), dict) else {}
    effective_metadata = (
        report.get("effective_metadata") if isinstance(report.get("effective_metadata"), dict) else {}
    )
    effective_sources = (
        report.get("effective_sources") if isinstance(report.get("effective_sources"), dict) else {}
    )
    recorded_override = (
        report.get("manual_override") if isinstance(report.get("manual_override"), dict) else {}
    )
    manual_override = {**recorded_override, **(metadata_override or {})}
    confidence_map = ai_metadata.get("confidence") if isinstance(ai_metadata.get("confidence"), dict) else {}
    evidence_map = ai_metadata.get("evidence") if isinstance(ai_metadata.get("evidence"), dict) else {}
    ai_status = _clean_text(ai_metadata.get("status")) or "not_run"
    ai_error = _clean_text(ai_metadata.get("error"))

    rows: list[dict[str, Any]] = []
    review_fields: list[str] = []
    ai_used_fields: list[str] = []

    for field in METADATA_FIELDS:
        effective_value = effective_metadata.get(field)
        effective_source = _clean_text(effective_sources.get(field))
        ai_value = ai_metadata.get(field)
        ai_confidence = _normalize_metadata_confidence(confidence_map.get(field))
        ai_evidence = _clean_text(evidence_map.get(field))
        manual_override_value = manual_override.get(field)
        if manual_override_value is not None:
            effective_value = manual_override_value
            effective_source = "manual_override"

        if not any(
            value is not None and value != ""
            for value in (
                effective_value,
                ai_value,
                manual_override_value,
                ai_evidence,
            )
        ) and effective_source is None:
            continue

        review_needed = False
        if effective_source == "manual_override":
            review_needed = False
        elif effective_source == "ai":
            ai_used_fields.append(field)
            review_needed = ai_confidence != "high" or ai_evidence is None
        elif ai_value is not None and ai_confidence in {"medium", "low"}:
            review_needed = True

        if review_needed:
            review_fields.append(field)

        rows.append(
            {
                "field": field,
                "label": METADATA_FIELD_LABELS.get(field, field),
                "effective_value": effective_value,
                "effective_source": effective_source,
                "ai_value": ai_value,
                "ai_confidence": ai_confidence,
                "ai_evidence": ai_evidence,
                "manual_override_value": manual_override_value,
                "review_needed": review_needed,
            }
        )

    summary = None
    if review_fields:
        summary = ", ".join(
            f"{METADATA_FIELD_LABELS.get(field, field)}={_normalize_metadata_confidence(confidence_map.get(field))}"
            for field in review_fields
        )
    elif ai_used_fields:
        summary = "AI verified"
    elif manual_override:
        summary = "Manual override"
    elif ai_error:
        summary = f"AI skipped: {ai_error}"

    return {
        "metadata_ai_status": ai_status,
        "metadata_ai_error": ai_error,
        "metadata_review_needed": bool(review_fields),
        "metadata_review_fields": review_fields,
        "metadata_review_rows": rows,
        "metadata_review_summary": summary,
    }


def _rights_assessment_label(assessment: str | None) -> str:
    if assessment == "likely_public_domain_us":
        return "Likely public domain (US)"
    if assessment == "likely_public_domain_life_plus_70":
        return "Likely public domain (life+70)"
    return "Rights uncertain"


def _rights_review_from_report(
    metadata_report: dict[str, Any] | None,
    rights_report: dict[str, Any] | None,
) -> dict[str, Any]:
    report = metadata_report if isinstance(metadata_report, dict) else {}
    rights_info = rights_report if isinstance(rights_report, dict) else {}
    rights_sources = (
        report.get("rights_sources") if isinstance(report.get("rights_sources"), dict) else {}
    )

    assessment = _clean_text(rights_info.get("assessment")) or "unknown"
    reason = _clean_text(rights_info.get("reason"))
    source_summary = _clean_text(rights_info.get("source_summary"))
    warnings = rights_info.get("warnings") if isinstance(rights_info.get("warnings"), list) else []
    warnings = [_clean_text(item) for item in warnings]
    warnings = [item for item in warnings if item]

    if source_summary is None and rights_sources:
        source_parts = []
        for field in ("author", "publication_year", "death_year"):
            source = _clean_text(rights_sources.get(field))
            if source:
                source_parts.append(f"{METADATA_FIELD_LABELS.get(field, field)}={source}")
        source_summary = ", ".join(source_parts) if source_parts else None

    inferred_review = False
    if any(_clean_text(rights_sources.get(field)) == "ai_high" for field in ("author", "publication_year", "death_year")):
        inferred_review = True
    raw_needs_manual_review = rights_info.get("needs_manual_review")
    if isinstance(raw_needs_manual_review, bool):
        needs_manual_review = raw_needs_manual_review
    else:
        needs_manual_review = inferred_review or (
            assessment == "unknown" and bool(source_summary or reason or warnings)
        )

    summary = None
    assessment_label = _rights_assessment_label(assessment)
    if needs_manual_review:
        summary = f"Review required: {assessment_label}"
        if source_summary:
            summary += f" ({source_summary})"
    elif assessment != "unknown":
        summary = assessment_label
    elif reason:
        summary = reason

    if warnings:
        warning_suffix = warnings[0]
        summary = f"{summary}; {warning_suffix}" if summary else warning_suffix

    return {
        "rights_assessment": assessment,
        "rights_reason": reason,
        "rights_needs_manual_review": needs_manual_review,
        "rights_source_summary": source_summary,
        "rights_warning_rows": warnings,
        "rights_review_summary": summary,
    }


def _publish_issue_from_report(publish_report: dict[str, Any] | None) -> dict[str, str | None]:
    report = publish_report if isinstance(publish_report, dict) else {}
    status = str(report.get("status") or "missing")
    reason = str(report.get("reason")).strip() if report.get("reason") else None
    health_check = report.get("health_check") if isinstance(report.get("health_check"), dict) else {}
    health_status = str(health_check.get("status") or "").strip().lower()
    health_reason = (
        str(health_check.get("reason")).strip() if health_check.get("reason") else None
    )

    issue_type: str | None = None
    issue_label: str | None = None
    issue_detail = health_reason or reason

    if health_status == "dns_failed":
        issue_type = "dns"
        issue_label = "DNS"
    elif health_status == "auth_failed":
        issue_type = "auth"
        issue_label = "Auth"
    elif health_status == "missing_credentials":
        issue_type = "credentials"
        issue_label = "Credentials"
    elif health_status == "api_failed":
        issue_type = "api"
        issue_label = "API"
    elif reason:
        lower = reason.lower()
        if "could not resolve" in lower or "name or service not known" in lower or "dns" in lower:
            issue_type = "dns"
            issue_label = "DNS"
        elif (
            "service key" in lower
            or "(401)" in lower
            or "(403)" in lower
            or "unauthorized" in lower
            or "forbidden" in lower
        ):
            issue_type = "auth"
            issue_label = "Auth"
        elif (
            lower.startswith("missing ")
            or " no page_" in lower
            or "no page_" in lower
            or " not found" in lower
            or lower.endswith(" not found")
        ):
            issue_type = "missing_file"
            issue_label = "Missing file"
        elif status == "failed":
            issue_type = "publish_error"
            issue_label = "Publish error"

    issue_summary = None
    if issue_label and issue_detail:
        issue_summary = f"{issue_label}: {issue_detail}"
    elif issue_detail:
        issue_summary = issue_detail

    return {
        "publish_issue_type": issue_type,
        "publish_issue_label": issue_label,
        "publish_issue_detail": issue_detail,
        "publish_issue_summary": issue_summary,
    }


def _normalize_compile_warning(line: str) -> str | None:
    text = line.strip()
    if not text:
        return None
    if text.startswith("Overfull \\hbox"):
        return "Overfull hbox"
    if text.startswith("Underfull \\hbox"):
        return "Underfull hbox"
    if text.startswith("Missing character:"):
        return "Missing character"
    package_warning = re.match(r"^Package ([^\s]+) Warning:\s*(.+)$", text)
    if package_warning:
        package_name, message = package_warning.groups()
        message = re.sub(r"\s+on input line \d+\.?$", "", message).strip()
        return f"{package_name} warning: {message}"
    latex_warning = re.match(r"^LaTeX Warning:\s*(.+)$", text)
    if latex_warning:
        message = re.sub(r"\s+on input line \d+\.?$", "", latex_warning.group(1)).strip()
        return f"LaTeX warning: {message}"
    package_info = re.match(r"^Package ([^\s]+) Info:\s*(.+ is missing)\s*$", text)
    if package_info:
        package_name, message = package_info.groups()
        return f"{package_name} info: {message}"
    return None


def _truncate_summary_text(value: str, max_length: int = 96) -> str:
    return value if len(value) <= max_length else value[: max_length - 3].rstrip() + "..."


def _compile_warnings_from_output(output_path: Path) -> dict[str, Any]:
    patterns = (
        ("*_digitalized.log", "digitalized", "warning"),
        ("*_Korean.log", "korean", "warning"),
        ("*_digitalized_error.log", "digitalized", "error"),
        ("*_Korean_error.log", "korean", "error"),
    )
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}

    for glob_pattern, target, severity in patterns:
        for path in sorted(output_path.glob(glob_pattern)):
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for line in lines:
                normalized = _normalize_compile_warning(line)
                if normalized is None:
                    continue
                key = (target, severity, normalized)
                row = grouped.setdefault(
                    key,
                    {
                        "target": target,
                        "severity": severity,
                        "message": normalized,
                        "count": 0,
                        "path": str(path.resolve()),
                    },
                )
                row["count"] += 1

    rows = sorted(
        grouped.values(),
        key=lambda item: (
            0 if item["severity"] == "error" else 1,
            -item["count"],
            item["target"],
            item["message"],
        ),
    )
    summary = None
    if rows:
        summary = ", ".join(
            f"{item['target']}: {_truncate_summary_text(item['message'])} x{item['count']}"
            for item in rows[:3]
        )
    return {
        "compile_warning_count": sum(item["count"] for item in rows),
        "compile_warning_rows": rows,
        "compile_warning_summary": summary,
    }


def _next_action(summary: dict[str, Any]) -> str:
    if summary["hung_suspected"]:
        return "Inspect hung pipeline"
    if summary["current_stage"] and summary["current_stage"] != "complete":
        return "Wait for pipeline"
    if summary["failed_pages"]:
        return "Retry failed pages"
    if not summary["has_quality_report"]:
        return "Run pipeline"
    if not summary["digitalized_compiled"] or not summary["korean_compiled"]:
        return "Fix PDF compilation"
    if summary.get("rights_needs_manual_review"):
        return "Review rights metadata"
    if summary.get("publish_issue_type") == "missing_file":
        return "Fix publish inputs"
    if summary.get("publish_issue_type") in {"dns", "api"}:
        return "Fix Supabase connectivity"
    if summary.get("publish_issue_type") in {"auth", "credentials"}:
        return "Fix Supabase credentials"
    if summary["publish_status"] == "failed":
        return "Retry publish"
    if summary["publish_status"] != "published":
        return "Publish to Supabase"
    return "Published"


def _priority_rank(summary: dict[str, Any]) -> int:
    if summary["hung_suspected"]:
        return 0
    if summary["current_stage"] and summary["current_stage"] != "complete":
        return 1
    if summary["failed_pages"]:
        return 2
    if not summary["has_quality_report"]:
        return 3
    if not summary["digitalized_compiled"] or not summary["korean_compiled"]:
        return 4
    if summary.get("rights_needs_manual_review"):
        return 5
    if summary.get("publish_issue_type") in {"missing_file", "dns", "api", "auth", "credentials"}:
        return 6
    if summary["publish_status"] == "failed":
        return 6
    if summary.get("compile_warning_count"):
        return 7
    if summary["publish_status"] != "published":
        return 7
    return 8


def summarize_output_directory(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    if not output_path.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {output_path}")

    quality_report_path, quality_report = _first_report(output_path, "*_quality_report.json")
    publish_report_path, publish_report = _first_report(output_path, "*_publish_report.json")
    pipeline_state_path, pipeline_state = _first_report(output_path, "*_pipeline_state.json")
    metadata_report_path, metadata_report = _first_report(output_path, "*_metadata.json")
    rights_report_path, rights_report = _first_report(output_path, "*_rights_check.json")
    metadata_override_report_path, metadata_override = _load_metadata_override(output_path)
    metadata_review = _metadata_review_from_report(metadata_report, metadata_override)
    rights_review = _rights_review_from_report(metadata_report, rights_report)
    compile_warning_review = _compile_warnings_from_output(output_path)

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
    publish_issue = _publish_issue_from_report(publish_report)
    partial_output = bool((quality_report or {}).get("transcription", {}).get("partial_output")) or bool(failed_pages)
    runtime_settings = (
        (pipeline_state or {}).get("runtime_settings")
        if isinstance((pipeline_state or {}).get("runtime_settings"), dict)
        else {}
    )
    current_stage = (pipeline_state or {}).get("current_stage")
    last_progress_at = (pipeline_state or {}).get("last_progress_at")
    seconds_since_progress, hung_threshold_sec, hung_suspected = _progress_health(
        current_stage,
        last_progress_at,
        runtime_settings,
    )

    summary = {
        "folder_name": output_path.name,
        "path": str(output_path.resolve()),
        "title": _infer_title(
            output_path,
            quality_report,
            metadata_report,
            pipeline_state,
            metadata_override,
        ),
        "has_quality_report": quality_report_path is not None,
        "has_publish_report": publish_report_path is not None,
        "quality_report_path": str(quality_report_path.resolve()) if quality_report_path else None,
        "publish_report_path": str(publish_report_path.resolve()) if publish_report_path else None,
        "pipeline_state_path": str(pipeline_state_path.resolve()) if pipeline_state_path else None,
        "metadata_report_path": str(metadata_report_path.resolve()) if metadata_report_path else None,
        "rights_report_path": str(rights_report_path.resolve()) if rights_report_path else None,
        "metadata_override_path": (
            str(metadata_override_report_path.resolve())
            if metadata_override_report_path
            else None
        ),
        "metadata_override_fields": sorted(metadata_override),
        **metadata_review,
        **rights_review,
        **compile_warning_review,
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
        **publish_issue,
        "published_at": (publish_report or {}).get("published_at"),
        "slug": (publish_report or {}).get("slug"),
        "current_stage": current_stage,
        "last_successful_stage": (pipeline_state or {}).get("last_successful_stage"),
        "last_error": (pipeline_state or {}).get("last_error"),
        "last_progress_at": last_progress_at,
        "last_progress_note": (pipeline_state or {}).get("last_progress_note"),
        "stdout_log_path": _normalize_path_string((pipeline_state or {}).get("stdout_log_path")),
        "stderr_log_path": _normalize_path_string((pipeline_state or {}).get("stderr_log_path")),
        "runtime_settings": runtime_settings,
        "api_timeout_sec": runtime_settings.get("api_timeout_sec"),
        "api_retry_attempts": runtime_settings.get("api_retry_attempts"),
        "latex_compile_timeout_sec": runtime_settings.get("latex_compile_timeout_sec"),
        "seconds_since_progress": seconds_since_progress,
        "hung_threshold_sec": hung_threshold_sec,
        "hung_suspected": hung_suspected,
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
            "metadata_review_outputs": sum(1 for item in documents if item["metadata_review_needed"]),
            "rights_review_outputs": sum(1 for item in documents if item["rights_needs_manual_review"]),
            "compile_warning_outputs": sum(1 for item in documents if item["compile_warning_count"]),
            "partial_outputs": sum(1 for item in documents if item["partial_output"]),
            "hung_suspected_outputs": sum(1 for item in documents if item["hung_suspected"]),
            "missing_quality_reports": sum(1 for item in documents if not item["has_quality_report"]),
        },
    }

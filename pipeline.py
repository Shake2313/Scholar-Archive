#!/usr/bin/env python3
"""
PDF Digitization & Korean Translation Pipeline v2.0

Usage:
    python pipeline.py --input paper.pdf --name "PaperName" --output ./output
    python pipeline.py --input paper.pdf --name "PaperName" --output ./output --pages 1-3
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import json
import os
import re
import shutil
import sys
from datetime import datetime

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from prompts import (
    METADATA_SYS, METADATA_USR,
    STEP1_SYS, STEP1_USR,
    STEP2_SYS, STEP2_USR,
    STEP3_SYS, STEP3_USR,
    STEP6_SYS, STEP6_USR,
    STEP7_SYS, STEP7_USR,
)
from publish import (
    apply_metadata_override,
    build_publish_bundle,
    load_metadata_override,
    metadata_override_path,
    publish_bundle_to_supabase,
    save_publish_report,
)
from steps import (
    API_RETRY_ATTEMPTS,
    API_TIMEOUT_SEC,
    pdf_to_images,
    get_pdf_page_count,
    infer_source_layout_profile,
    call_vision,
    call_text,
    TRANSLATION_MODEL,
    run_preflight_checks,
    extract_block,
    normalize_latex_source,
    is_latex_document,
    auto_fix_loop,
    apply_source_layout_profile,
    merge_pages,
    finalize_report,
    _latex_compile_timeout_sec,
)


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
METADATA_CONFIDENCE = {"high", "medium", "low", "none"}

RUN_MODE_FULL = "full"
RUN_MODE_METADATA_ONLY = "metadata_only"
RUN_MODE_TRANSLATION_ONLY = "translation_only"
RUN_MODE_KOREAN_PDF_ONLY = "korean_pdf_only"


def resolve_run_mode(
    *,
    metadata_only: bool = False,
    translation_only: bool = False,
    korean_pdf_only: bool = False,
) -> str:
    selected = [
        mode
        for enabled, mode in (
            (metadata_only, RUN_MODE_METADATA_ONLY),
            (translation_only, RUN_MODE_TRANSLATION_ONLY),
            (korean_pdf_only, RUN_MODE_KOREAN_PDF_ONLY),
        )
        if enabled
    ]
    if len(selected) > 1:
        raise ValueError("Choose only one stage-only run mode at a time.")
    return selected[0] if selected else RUN_MODE_FULL


def preflight_kwargs_for_run_mode(run_mode: str) -> dict:
    mapping = {
        RUN_MODE_FULL: {
            "needs_genai": True,
            "needs_pdf": True,
            "latex_compilers": ("pdflatex", "xelatex"),
        },
        RUN_MODE_METADATA_ONLY: {
            "needs_genai": True,
            "needs_pdf": False,
            "latex_compilers": (),
        },
        RUN_MODE_TRANSLATION_ONLY: {
            "needs_genai": True,
            "needs_pdf": False,
            "latex_compilers": (),
        },
        RUN_MODE_KOREAN_PDF_ONLY: {
            "needs_genai": False,
            "needs_pdf": False,
            "latex_compilers": ("xelatex",),
        },
    }
    if run_mode not in mapping:
        raise ValueError(f"Unsupported run mode: {run_mode}")
    return mapping[run_mode]


def runtime_settings_snapshot(
    *,
    workers: int,
    translation_chunk_pages: int,
    resume: bool,
    retry_pages: str | None,
    publish_enabled: bool,
    run_mode: str,
    force_refresh_images: bool,
    force_refresh_metadata: bool,
) -> dict:
    return {
        "run_mode": run_mode,
        "resume": resume,
        "retry_pages": retry_pages,
        "workers": workers,
        "translation_chunk_pages": translation_chunk_pages,
        "publish_enabled": publish_enabled,
        "force_refresh_images": force_refresh_images,
        "force_refresh_metadata": force_refresh_metadata,
        "api_timeout_sec": API_TIMEOUT_SEC,
        "api_retry_attempts": API_RETRY_ATTEMPTS,
        "latex_compile_timeout_sec": _latex_compile_timeout_sec(),
    }


def pipeline_state_path(output_dir: str, name: str) -> str:
    return os.path.join(output_dir, f"{name}_pipeline_state.json")


def metadata_report_path(output_dir: str, name: str) -> str:
    return os.path.join(output_dir, f"{name}_metadata.json")


def pipeline_stdout_log_path(output_dir: str, name: str) -> str:
    return os.path.abspath(os.path.join(output_dir, f"{name}_pipeline_stdout.log"))


def pipeline_stderr_log_path(output_dir: str, name: str) -> str:
    return os.path.abspath(os.path.join(output_dir, f"{name}_pipeline_stderr.log"))


def load_pipeline_state(output_dir: str, name: str) -> dict:
    path = pipeline_state_path(output_dir, name)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_pipeline_state(output_dir: str, name: str, state: dict) -> str:
    path = pipeline_state_path(output_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return path


def mark_pipeline_stage(
    state: dict,
    output_dir: str,
    name: str,
    *,
    current_stage: str | None = None,
    last_successful_stage: str | None = None,
    last_error: str | None = None,
    extra: dict | None = None,
) -> str:
    now = datetime.now().isoformat()
    if current_stage is not None:
        state["current_stage"] = current_stage
    if last_successful_stage is not None:
        state["last_successful_stage"] = last_successful_stage
    if last_error is not None:
        state["last_error"] = last_error
    if extra:
        state.update(extra)
    state["last_progress_at"] = now
    state["checked_at"] = now
    return save_pipeline_state(output_dir, name, state)


def record_pipeline_progress(
    state: dict,
    output_dir: str,
    name: str,
    note: str,
) -> str:
    return mark_pipeline_stage(
        state,
        output_dir,
        name,
        extra={"last_progress_note": note},
    )


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)
        return len(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()

    def reconfigure(self, **kwargs):
        for stream in self.streams:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(**kwargs)
        return self


@contextmanager
def redirect_pipeline_output(
    output_dir: str,
    name: str,
    *,
    stdout_stream=None,
    stderr_stream=None,
):
    os.makedirs(output_dir, exist_ok=True)
    stdout_path = pipeline_stdout_log_path(output_dir, name)
    stderr_path = pipeline_stderr_log_path(output_dir, name)
    with open(stdout_path, "w", encoding="utf-8") as stdout_log, open(
        stderr_path, "w", encoding="utf-8"
    ) as stderr_log:
        stdout_target = TeeStream(
            *(stream for stream in (stdout_stream, stdout_log) if stream is not None)
        )
        stderr_target = TeeStream(
            *(stream for stream in (stderr_stream, stderr_log) if stream is not None)
        )
        with redirect_stdout(stdout_target), redirect_stderr(stderr_target):
            yield stdout_path, stderr_path


def copy_source_pdf(input_pdf: str, output_dir: str, name: str) -> str:
    source_copy_path = os.path.join(output_dir, f"{name}_source.pdf")
    if os.path.abspath(input_pdf) != os.path.abspath(source_copy_path):
        shutil.copyfile(input_pdf, source_copy_path)
    return source_copy_path


def _clean_metadata_value(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_year(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1500 <= value <= 2100 else None
    text = str(value).strip()
    match = re.search(r"\b(1[5-9]\d{2}|20\d{2}|2100)\b", text)
    if not match:
        return None
    year = int(match.group(1))
    return year if 1500 <= year <= 2100 else None


def extract_pdf_metadata(pdf_path: str) -> dict:
    """Read raw PDF metadata and keep the common bibliographic fields."""
    try:
        import fitz
    except Exception:
        return {}

    raw = {}
    try:
        doc = fitz.open(pdf_path)
        raw = doc.metadata or {}
        doc.close()
    except Exception:
        return {}

    cleaned = {}
    for key in ("title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate"):
        value = _clean_metadata_value(raw.get(key))
        if value is not None:
            cleaned[key] = value
    return cleaned


def extract_json_object(text: str) -> dict | None:
    """Extract the first JSON object from a model response."""
    if not text:
        return None
    candidate = text.strip()
    candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s*```$", "", candidate)
    decoder = json.JSONDecoder()
    for idx, char in enumerate(candidate):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(candidate[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def render_metadata_prompt(
    paper_name: str,
    raw_pdf_metadata_json: str,
    structure_json: str,
    first_page_latex: str,
) -> str:
    """Render the metadata prompt without interpreting JSON braces as format fields."""
    return (
        METADATA_USR
        .replace("{paper_name}", paper_name)
        .replace("{raw_pdf_metadata_json}", raw_pdf_metadata_json)
        .replace("{structure_json}", structure_json)
        .replace("{first_page_latex}", first_page_latex)
    )


def normalize_ai_metadata(raw: dict | None) -> dict:
    """Coerce AI metadata into a stable shape."""
    data = raw if isinstance(raw, dict) else {}
    confidence_raw = data.get("confidence") if isinstance(data.get("confidence"), dict) else {}
    evidence_raw = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}

    normalized = {}
    for field in METADATA_FIELDS:
        value = data.get(field)
        if field.endswith("_year"):
            normalized[field] = _coerce_year(value)
        else:
            normalized[field] = _clean_metadata_value(value)

    normalized["confidence"] = {}
    normalized["evidence"] = {}
    for field in METADATA_FIELDS:
        conf = str(confidence_raw.get(field) or "").strip().lower()
        if conf not in METADATA_CONFIDENCE:
            conf = "low" if normalized[field] is not None else "none"
        normalized["confidence"][field] = conf
        normalized["evidence"][field] = _clean_metadata_value(evidence_raw.get(field))
    return normalized


def normalize_recorded_ai_metadata(raw: dict | None) -> dict:
    normalized = normalize_ai_metadata(raw)
    payload = raw if isinstance(raw, dict) else {}
    normalized["status"] = _clean_metadata_value(payload.get("status")) or "not_run"
    normalized["error"] = _clean_metadata_value(payload.get("error"))
    return normalized


def infer_metadata_from_structure(structure_json: str) -> dict:
    """Infer basic metadata from STEP 1 structure JSON without another model call."""
    try:
        data = json.loads(structure_json)
    except Exception:
        return {field: None for field in ("title", "author", "publication_year", "death_year")}

    article_header = data.get("article_header", {}) if isinstance(data, dict) else {}
    title = _clean_metadata_value(article_header.get("title_text"))
    author_line = _clean_metadata_value(article_header.get("author_line"))
    author = None
    if author_line:
        author = re.sub(r"^(By|Von)\s+", "", author_line, flags=re.IGNORECASE)

    blob = json.dumps(data, ensure_ascii=False)
    years = re.findall(r"\b(1[6-9]\d{2}|20\d{2})\b", blob)
    publication_year = int(years[0]) if years else None

    known_death_years = {
        "emmy noether": 1935,
        "albert einstein": 1955,
    }
    death_year = known_death_years.get(author.lower()) if author else None
    return {
        "title": title,
        "author": author,
        "publication_year": publication_year,
        "death_year": death_year,
    }


def infer_metadata_with_ai(
    paper_name: str,
    raw_pdf_metadata: dict,
    structure_json: str,
    first_page_latex: str,
) -> dict:
    """Ask the model to infer bibliographic metadata from page evidence."""
    prompt = render_metadata_prompt(
        paper_name=paper_name,
        raw_pdf_metadata_json=json.dumps(raw_pdf_metadata or {}, ensure_ascii=False, indent=2),
        structure_json=structure_json[:12000],
        first_page_latex=first_page_latex[:12000],
    )
    try:
        response = call_text(METADATA_SYS, prompt, max_tokens=4096)
        payload = extract_json_object(response)
        normalized = normalize_ai_metadata(payload)
        normalized["status"] = "ok" if payload else "empty"
        normalized["error"] = None if payload else "Could not parse metadata JSON response."
        return normalized
    except Exception as exc:
        normalized = normalize_ai_metadata({})
        normalized["status"] = "error"
        normalized["error"] = str(exc).strip() or exc.__class__.__name__
        return normalized


def _should_use_ai_metadata(field: str, ai_metadata: dict, min_confidence: set[str]) -> bool:
    value = ai_metadata.get(field)
    if value is None:
        return False
    confidence = ai_metadata.get("confidence", {}).get(field, "none")
    return confidence in min_confidence


def build_effective_metadata(
    user_author: str | None,
    user_publication_year: int | None,
    user_death_year: int | None,
    raw_pdf_metadata: dict,
    deterministic_metadata: dict,
    ai_metadata: dict,
) -> tuple[dict, dict]:
    """Combine user, raw PDF, deterministic, and AI metadata for display/storage."""
    effective = {
        "title": None,
        "author": None,
        "publication_year": None,
        "death_year": None,
        "journal_or_book": None,
        "volume": None,
        "issue": None,
        "pages": None,
        "language": None,
        "doi": None,
    }
    sources = {field: None for field in effective}

    def assign(field: str, value, source: str):
        if value is None or effective[field] is not None:
            return
        effective[field] = value
        sources[field] = source

    assign("title", raw_pdf_metadata.get("title"), "pdf")
    assign("title", deterministic_metadata.get("title"), "structure")
    if _should_use_ai_metadata("title", ai_metadata, {"high", "medium"}):
        assign("title", ai_metadata.get("title"), "ai")

    assign("author", _clean_metadata_value(user_author), "user")
    assign("author", raw_pdf_metadata.get("author"), "pdf")
    assign("author", deterministic_metadata.get("author"), "structure")
    if _should_use_ai_metadata("author", ai_metadata, {"high", "medium"}):
        assign("author", ai_metadata.get("author"), "ai")

    assign("publication_year", _coerce_year(user_publication_year), "user")
    assign("publication_year", deterministic_metadata.get("publication_year"), "structure")
    if _should_use_ai_metadata("publication_year", ai_metadata, {"high", "medium"}):
        assign("publication_year", ai_metadata.get("publication_year"), "ai")

    assign("death_year", _coerce_year(user_death_year), "user")
    assign("death_year", deterministic_metadata.get("death_year"), "structure")
    if _should_use_ai_metadata("death_year", ai_metadata, {"high", "medium"}):
        assign("death_year", ai_metadata.get("death_year"), "ai")

    for field in ("journal_or_book", "volume", "issue", "pages", "language", "doi"):
        if _should_use_ai_metadata(field, ai_metadata, {"high", "medium"}):
            assign(field, ai_metadata.get(field), "ai")

    return effective, sources


def build_rights_metadata(
    user_author: str | None,
    user_publication_year: int | None,
    user_death_year: int | None,
    raw_pdf_metadata: dict,
    deterministic_metadata: dict,
    ai_metadata: dict,
) -> tuple[dict, dict]:
    """Choose conservative metadata values suitable for rights heuristics."""
    values = {
        "author": None,
        "publication_year": None,
        "death_year": None,
    }
    sources = {field: None for field in values}

    def assign(field: str, value, source: str):
        if value is None or values[field] is not None:
            return
        values[field] = value
        sources[field] = source

    assign("author", _clean_metadata_value(user_author), "user")
    assign("publication_year", _coerce_year(user_publication_year), "user")
    assign("death_year", _coerce_year(user_death_year), "user")

    assign("author", raw_pdf_metadata.get("author"), "pdf")
    assign("author", deterministic_metadata.get("author"), "structure")
    assign("publication_year", deterministic_metadata.get("publication_year"), "structure")
    assign("death_year", deterministic_metadata.get("death_year"), "structure")

    if _should_use_ai_metadata("author", ai_metadata, {"high"}):
        assign("author", ai_metadata.get("author"), "ai_high")
    if _should_use_ai_metadata("publication_year", ai_metadata, {"high"}):
        assign("publication_year", ai_metadata.get("publication_year"), "ai_high")
    if _should_use_ai_metadata("death_year", ai_metadata, {"high"}):
        assign("death_year", ai_metadata.get("death_year"), "ai_high")

    return values, sources


def apply_manual_metadata_override(
    effective_metadata: dict,
    effective_sources: dict,
    rights_metadata: dict,
    rights_sources: dict,
    manual_override: dict,
) -> tuple[dict, dict, dict, dict]:
    normalized_override = apply_metadata_override({}, manual_override)
    if not normalized_override:
        return effective_metadata, effective_sources, rights_metadata, rights_sources

    effective = dict(effective_metadata)
    sources = dict(effective_sources)
    for field, value in normalized_override.items():
        effective[field] = value
        sources[field] = "manual_override"

    rights = dict(rights_metadata)
    right_sources = dict(rights_sources)
    for field in ("author", "publication_year", "death_year"):
        if field in normalized_override:
            rights[field] = normalized_override[field]
            right_sources[field] = "manual_override"
    return effective, sources, rights, right_sources


def save_metadata_report(output_dir: str, name: str, report: dict) -> str:
    path = metadata_report_path(output_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path


def load_metadata_report(output_dir: str, name: str) -> dict:
    path = metadata_report_path(output_dir, name)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def parse_page_range(pages_str: str, total: int) -> list[int]:
    """Parse page range string like '1-3' or '2,4,5' into 0-based indices."""
    indices = []
    for part in pages_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            for i in range(int(start), int(end) + 1):
                indices.append(i - 1)
        else:
            indices.append(int(part) - 1)
    return [i for i in indices if 0 <= i < total]


def assess_rights(
    author: str | None,
    publication_year: int | None,
    death_year: int | None,
) -> dict:
    """Simple rights-check heuristic for logging."""
    current_year = datetime.now().year
    result = {
        "author": author,
        "publication_year": publication_year,
        "death_year": death_year,
        "assessment": "unknown",
        "reason": "Insufficient metadata.",
    }
    if publication_year is not None and publication_year <= 1929:
        result["assessment"] = "likely_public_domain_us"
        result["reason"] = "Publication year is 1929 or earlier (US heuristic)."
        return result
    if death_year is not None and current_year - death_year >= 70:
        result["assessment"] = "likely_public_domain_life_plus_70"
        result["reason"] = "Author death year is at least 70 years ago."
        return result
    if publication_year is not None:
        result["reason"] = "Publication year alone was not enough for this heuristic."
    return result


def build_rights_context(rights_info: dict) -> str:
    """Build a rights-context note to attach to model prompts."""
    assessment = rights_info.get("assessment", "unknown")
    reason = rights_info.get("reason", "")
    author = rights_info.get("author")
    publication_year = rights_info.get("publication_year")
    death_year = rights_info.get("death_year")
    summary = (
        "RIGHTS CONTEXT:\n"
        f"- author: {author}\n"
        f"- publication_year: {publication_year}\n"
        f"- death_year: {death_year}\n"
        f"- assessment: {assessment}\n"
        f"- reason: {reason}\n"
    )
    if assessment.startswith("likely_public_domain"):
        summary += (
            "The user states this source is public-domain and authorizes faithful transcription.\n"
            "For this task, treat verbatim transcription as permitted.\n"
        )
    else:
        summary += (
            "Rights status is not confirmed as public-domain by heuristic.\n"
            "Proceed conservatively if policy restrictions apply.\n"
        )
    return summary


def split_latex_into_page_docs(source: str) -> list[str]:
    """Split a merged LaTeX document into page-like mini documents by \\newpage."""
    m_begin = re.search(r"\\begin\{document\}", source)
    m_end = re.search(r"\\end\{document\}\s*$", source)
    if not m_begin or not m_end:
        return [source]
    preamble = source[: m_begin.end()]
    body = source[m_begin.end(): m_end.start()]
    chunks = [c.strip() for c in re.split(r"\n\s*\\newpage\s*\n", body) if c.strip()]
    if not chunks:
        return [source]
    return [f"{preamble}\n{chunk}\n\\end{{document}}" for chunk in chunks]


def chunked(items: list, size: int) -> list[list]:
    if size <= 0:
        return [items]
    return [items[i:i + size] for i in range(0, len(items), size)]


def page_tex_path(output_dir: str, page_num: int) -> str:
    return os.path.join(output_dir, f"page_{page_num:03d}.tex")


def page_structure_path(output_dir: str, page_num: int) -> str:
    return os.path.join(output_dir, f"page_{page_num:03d}_structure.json")


def page_failure_path(output_dir: str, page_num: int) -> str:
    return os.path.join(output_dir, f"page_{page_num:03d}_failure.json")


def page_image_path(images_dir: str, page_num: int) -> str:
    return os.path.join(images_dir, f"page_{page_num:03d}.png")


def normalize_page_numbers(values) -> list[int]:
    if not isinstance(values, list):
        return []
    seen = set()
    page_numbers = []
    for value in values:
        try:
            page_num = int(value)
        except Exception:
            continue
        if page_num > 0 and page_num not in seen:
            seen.add(page_num)
            page_numbers.append(page_num)
    return page_numbers


def resolve_cached_source_pdf(output_dir: str, name: str, existing_state: dict) -> str | None:
    candidates = [
        existing_state.get("source_pdf"),
        os.path.join(output_dir, f"{name}_source.pdf"),
        existing_state.get("input_pdf"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return os.path.abspath(candidate)
    return None


def collect_cached_image_paths(images_dir: str, requested_page_numbers: list[int]) -> list[str]:
    image_paths = [page_image_path(images_dir, page_num) for page_num in requested_page_numbers]
    if image_paths and all(os.path.exists(path) for path in image_paths):
        return image_paths
    return []


def find_first_cached_page_artifacts(
    output_dir: str,
    candidate_page_numbers: list[int] | None = None,
) -> tuple[int, str, str]:
    preferred = normalize_page_numbers(candidate_page_numbers)
    discovered = []
    for path in sorted(
        name for name in os.listdir(output_dir) if re.fullmatch(r"page_\d{3}_structure\.json", name)
    ):
        discovered.append(int(path[5:8]))

    for page_num in preferred + [page for page in discovered if page not in preferred]:
        struct_path = page_structure_path(output_dir, page_num)
        tex_path = page_tex_path(output_dir, page_num)
        if not (os.path.exists(struct_path) and os.path.exists(tex_path)):
            continue
        with open(struct_path, encoding="utf-8") as f:
            structure_json = f.read()
        with open(tex_path, encoding="utf-8") as f:
            latex_source = normalize_latex_source(f.read())
        if not is_latex_document(latex_source):
            continue
        return page_num, structure_json, latex_source

    raise RuntimeError(
        "Metadata-only rerun requires at least one cached page structure JSON and valid page TeX."
    )


def should_reuse_cached_page(
    *,
    resume: bool,
    page_num: int,
    retry_page_numbers: set[int],
    struct_path: str,
    tex_path: str,
) -> bool:
    """Reuse cached page outputs only when the page is not being explicitly retried."""
    return (
        resume
        and page_num not in retry_page_numbers
        and os.path.exists(struct_path)
        and os.path.exists(tex_path)
    )


def should_include_page_in_merge(page_num: int, failure_by_page: dict[int, dict]) -> bool:
    """Exclude pages that failed in the current run even if stale TeX files still exist."""
    return page_num not in failure_by_page


def translate_digitalized_latex(
    digitalized_latex: str,
    translation_chunk_pages: int,
    progress_callback=None,
) -> tuple[str, list[str]]:
    page_docs = split_latex_into_page_docs(digitalized_latex)
    groups = chunked(page_docs, translation_chunk_pages) if len(page_docs) > translation_chunk_pages else [page_docs]

    translated_docs = []
    notes_all = []
    for chunk_idx, docs in enumerate(groups, start=1):
        if progress_callback:
            progress_callback(chunk_idx, len(groups))
        chunk_source = merge_pages(docs)
        print(f"  [TRANSLATE] Translating chunk {chunk_idx}/{len(groups)}...")
        step6_user = STEP6_USR.format(
            digitalized_latex_source=chunk_source,
        )
        translation_response = call_text(
            STEP6_SYS,
            step6_user,
            max_tokens=16384,
            model=TRANSLATION_MODEL,
        )
        chunk_korean = extract_block(translation_response, "BEGIN_KOREAN_LATEX")
        if not chunk_korean:
            print("  WARNING: Could not extract Korean LaTeX chunk. Using raw response.")
            chunk_korean = translation_response
        chunk_korean = normalize_latex_source(chunk_korean)
        translated_docs.append(chunk_korean)

        translation_notes = extract_block(translation_response, "TRANSLATION_NOTES")
        if translation_notes:
            notes_all.append(f"--- Chunk {chunk_idx} ---\n{translation_notes}")

    korean_latex = merge_pages(translated_docs) if len(translated_docs) > 1 else translated_docs[0]
    return korean_latex, notes_all


def run_metadata_only(
    *,
    name: str,
    output_dir: str,
    existing_state: dict,
    runtime_settings: dict,
    source_pdf_path: str | None,
    author: str | None,
    publication_year: int | None,
    death_year: int | None,
) -> None:
    print("\n[MODE] Running metadata-only rerun...")
    manual_override = load_metadata_override(output_dir, name)
    state = dict(existing_state)
    state.update(
        {
            "paper_name": name,
            "output_dir": os.path.abspath(output_dir),
            "source_pdf": source_pdf_path,
            "author": author,
            "publication_year": publication_year,
            "death_year": death_year,
            "run_mode": RUN_MODE_METADATA_ONLY,
            "stdout_log_path": pipeline_stdout_log_path(output_dir, name),
            "stderr_log_path": pipeline_stderr_log_path(output_dir, name),
            "runtime_settings": runtime_settings,
            "metadata_override_path": (
                metadata_override_path(output_dir, name)
                if manual_override
                else None
            ),
        }
    )
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="metadata",
        last_error=None,
        extra={"last_progress_note": "Refreshing metadata and rights check."},
    )
    raw_pdf_metadata = extract_pdf_metadata(source_pdf_path) if source_pdf_path else {}
    candidate_pages = normalize_page_numbers(existing_state.get("successful_pages")) or normalize_page_numbers(
        existing_state.get("requested_pages")
    )
    seed_page, structure_json, first_page_latex = find_first_cached_page_artifacts(
        output_dir,
        candidate_pages,
    )
    deterministic_metadata = infer_metadata_from_structure(structure_json)
    ai_metadata = infer_metadata_with_ai(
        name,
        raw_pdf_metadata,
        structure_json,
        first_page_latex,
    )
    effective_metadata, effective_sources = build_effective_metadata(
        author,
        publication_year,
        death_year,
        raw_pdf_metadata,
        deterministic_metadata,
        ai_metadata,
    )
    rights_metadata, rights_sources = build_rights_metadata(
        author,
        publication_year,
        death_year,
        raw_pdf_metadata,
        deterministic_metadata,
        ai_metadata,
    )
    effective_metadata, effective_sources, rights_metadata, rights_sources = apply_manual_metadata_override(
        effective_metadata,
        effective_sources,
        rights_metadata,
        rights_sources,
        manual_override,
    )
    metadata_report = {
        "checked_at": datetime.now().isoformat(),
        "paper_name": name,
        "raw_pdf_metadata": raw_pdf_metadata,
        "deterministic_inference": deterministic_metadata,
        "ai_inference": ai_metadata,
        "manual_override": manual_override,
        "effective_metadata": effective_metadata,
        "effective_sources": effective_sources,
        "rights_metadata": rights_metadata,
        "rights_sources": rights_sources,
    }
    metadata_report_path_value = save_metadata_report(output_dir, name, metadata_report)

    rights_info = {
        "checked_at": datetime.now().isoformat(),
        **assess_rights(
            rights_metadata.get("author"),
            rights_metadata.get("publication_year"),
            rights_metadata.get("death_year"),
        ),
    }
    rights_path = os.path.join(output_dir, f"{name}_rights_check.json")
    with open(rights_path, "w", encoding="utf-8") as f:
        json.dump(rights_info, f, ensure_ascii=False, indent=2)

    state.update(
        {
            "raw_pdf_metadata": raw_pdf_metadata,
            "metadata": effective_metadata,
            "metadata_sources": effective_sources,
            "rights_metadata": rights_metadata,
            "rights_metadata_sources": rights_sources,
            "metadata_report_path": metadata_report_path_value,
            "metadata_seed_page": seed_page,
            "last_completed_stage": "metadata",
        }
    )
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="complete",
        last_successful_stage="metadata",
        last_error=None,
        extra={"last_progress_note": "Metadata-only rerun complete."},
    )

    print(f"  [METADATA] Seed page: {seed_page}")
    print(f"  [METADATA] Report saved: {metadata_report_path_value}")
    if manual_override:
        print(
            "  [METADATA] Manual override fields: "
            + ", ".join(sorted(manual_override))
        )
    print(f"  [RIGHTS] Assessment: {rights_info['assessment']} ({rights_info['reason']})")
    print("  [MODE] Metadata-only rerun complete. Downstream PDFs/publish were not refreshed.")


def run_translation_only(
    *,
    name: str,
    output_dir: str,
    existing_state: dict,
    runtime_settings: dict,
    translation_chunk_pages: int,
) -> None:
    print("\n[MODE] Running translation-only rerun...")
    final_dig_tex = os.path.join(output_dir, f"{name}_digitalized.tex")
    if not os.path.exists(final_dig_tex):
        raise RuntimeError(
            "Translation-only rerun requires an existing digitalized TeX file."
        )
    with open(final_dig_tex, encoding="utf-8") as f:
        final_dig_latex = normalize_latex_source(f.read())
    if not is_latex_document(final_dig_latex):
        raise RuntimeError("Cached digitalized TeX is malformed and cannot be translated.")

    print(f"  [TRANSLATE] Model: {TRANSLATION_MODEL}")
    state = dict(existing_state)
    state.update(
        {
            "paper_name": name,
            "output_dir": os.path.abspath(output_dir),
            "translation_chunk_pages": translation_chunk_pages,
            "translation_model": TRANSLATION_MODEL,
            "run_mode": RUN_MODE_TRANSLATION_ONLY,
            "stdout_log_path": pipeline_stdout_log_path(output_dir, name),
            "stderr_log_path": pipeline_stderr_log_path(output_dir, name),
            "runtime_settings": runtime_settings,
        }
    )
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="translation",
        last_error=None,
        extra={"last_progress_note": "Translating Korean LaTeX."},
    )
    korean_latex, notes_all = translate_digitalized_latex(
        final_dig_latex,
        translation_chunk_pages,
        progress_callback=lambda chunk_idx, total_chunks: record_pipeline_progress(
            state,
            output_dir,
            name,
            f"Translating chunk {chunk_idx}/{total_chunks}.",
        ),
    )

    korean_tex_path = os.path.join(output_dir, f"{name}_Korean.tex")
    with open(korean_tex_path, "w", encoding="utf-8") as f:
        f.write(korean_latex)

    tnotes_path = os.path.join(output_dir, f"{name}_translation_notes.txt")
    if notes_all:
        with open(tnotes_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(notes_all))

    state.update(
        {
            "last_completed_stage": "translation",
            "korean_compiled": False,
        }
    )
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="complete",
        last_successful_stage="translation",
        last_error=None,
        extra={"last_progress_note": "Translation-only rerun complete."},
    )

    print(f"  [TRANSLATE] Korean LaTeX saved: {korean_tex_path}")
    print("  [MODE] Translation-only rerun complete. Korean PDF/report/publish were not refreshed.")


def run_korean_pdf_only(
    *,
    name: str,
    output_dir: str,
    existing_state: dict,
    runtime_settings: dict,
) -> None:
    print("\n[MODE] Running Korean PDF-only rerun...")
    state = dict(existing_state)
    state.update(
        {
            "paper_name": name,
            "output_dir": os.path.abspath(output_dir),
            "run_mode": RUN_MODE_KOREAN_PDF_ONLY,
            "stdout_log_path": pipeline_stdout_log_path(output_dir, name),
            "stderr_log_path": pipeline_stderr_log_path(output_dir, name),
            "runtime_settings": runtime_settings,
        }
    )
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="korean_pdf",
        last_error=None,
        extra={"last_progress_note": "Compiling Korean PDF."},
    )
    korean_tex_path = os.path.join(output_dir, f"{name}_Korean.tex")
    if not os.path.exists(korean_tex_path):
        raise RuntimeError("Korean PDF-only rerun requires an existing Korean TeX file.")
    with open(korean_tex_path, encoding="utf-8") as f:
        korean_latex = normalize_latex_source(f.read())
    if not is_latex_document(korean_latex):
        raise RuntimeError("Cached Korean TeX is malformed and cannot be compiled.")

    kor_pdf = os.path.join(output_dir, f"{name}_Korean.pdf")
    kor_err_log = os.path.join(output_dir, f"{name}_Korean_error.log")
    if os.path.exists(kor_err_log):
        print("\n[KOREAN PDF] Found previous error log; recompiling Korean PDF...")
    print("\n[KOREAN PDF] Compiling Korean PDF (xelatex)...")
    kor_ok, final_kor_latex, kor_pdf = auto_fix_loop(
        korean_latex,
        output_dir,
        f"{name}_Korean",
        max_attempts=5,
        compiler="xelatex",
        fix_system_prompt=STEP7_SYS,
        fix_user_template=STEP7_USR,
        double_compile=False,
    )

    with open(korean_tex_path, "w", encoding="utf-8") as f:
        f.write(final_kor_latex)

    requested_pages = normalize_page_numbers(existing_state.get("requested_pages"))
    successful_pages = normalize_page_numbers(existing_state.get("successful_pages"))
    failed_pages = normalize_page_numbers(existing_state.get("failed_pages"))
    num_pages = len(requested_pages) or len(successful_pages) + len(failed_pages)
    if num_pages <= 0:
        num_pages = len(split_latex_into_page_docs(final_kor_latex))

    dig_pdf = os.path.join(output_dir, f"{name}_digitalized.pdf")
    dig_err_log = os.path.join(output_dir, f"{name}_digitalized_error.log")
    dig_ok = existing_state.get("digitalized_compiled")
    if not isinstance(dig_ok, bool):
        dig_ok = os.path.exists(dig_pdf) and not os.path.exists(dig_err_log)

    quality_report_path_value = finalize_report(
        name,
        num_pages,
        dig_ok,
        kor_ok,
        output_dir,
        successful_pages=len(successful_pages) or max(0, num_pages - len(failed_pages)),
        failed_pages=failed_pages,
    )

    state.update(
        {
            "korean_compiled": kor_ok,
            "quality_report_path": quality_report_path_value,
            "last_completed_stage": "korean_pdf",
        }
    )
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="complete",
        last_successful_stage="korean_pdf" if kor_ok else None,
        last_error=None if kor_ok else "Korean PDF compilation failed.",
        extra={"last_progress_note": "Korean PDF-only rerun complete."},
    )

    if kor_ok:
        print(f"  Korean PDF: {kor_pdf}")
    else:
        print("  WARNING: Korean PDF compilation failed.")
    print(f"  [REPORT] Quality report saved: {quality_report_path_value}")
    print("  [MODE] Korean PDF-only rerun complete. Publish was not refreshed.")


def run_pipeline(
    input_pdf: str | None,
    name: str,
    output_dir: str,
    pages: str | None = None,
    author: str | None = None,
    publication_year: int | None = None,
    death_year: int | None = None,
    workers: int = 4,
    resume: bool = True,
    translation_chunk_pages: int = 4,
    retry_pages: str | None = None,
    publish_enabled: bool = True,
    run_mode: str = RUN_MODE_FULL,
    force_refresh_images: bool = False,
    force_refresh_metadata: bool = False,
):
    """Run the full STEP 0 ??8 pipeline."""
    print("[PREFLIGHT] Checking environment...")
    preflight = run_preflight_checks(**preflight_kwargs_for_run_mode(run_mode))
    for check in preflight["checks"]:
        print(f"  [{check['status'].upper()}] {check['name']}: {check['message']}")
    if not preflight["ok"]:
        failures = [
            f"{check['name']}: {check['message']}"
            for check in preflight["checks"]
            if check["status"] == "error"
        ]
        raise RuntimeError(
            "Preflight failed:\n- " + "\n- ".join(failures)
        )

    os.makedirs(output_dir, exist_ok=True)
    existing_state = load_pipeline_state(output_dir, name)
    settings_snapshot = runtime_settings_snapshot(
        workers=workers,
        translation_chunk_pages=translation_chunk_pages,
        resume=resume,
        retry_pages=retry_pages,
        publish_enabled=publish_enabled,
        run_mode=run_mode,
        force_refresh_images=force_refresh_images,
        force_refresh_metadata=force_refresh_metadata,
    )
    if run_mode != RUN_MODE_FULL and (pages or retry_pages):
        raise ValueError("Stage-only reruns do not support --pages or --retry-pages.")

    source_pdf_path = None
    if run_mode == RUN_MODE_FULL:
        if not input_pdf:
            raise ValueError("Full pipeline runs require an input PDF path.")
        source_pdf_path = copy_source_pdf(input_pdf, output_dir, name)
    else:
        source_pdf_path = resolve_cached_source_pdf(output_dir, name, existing_state)
        if publish_enabled:
            print("[MODE] Stage-only reruns skip publish even if publish is enabled.")
        publish_enabled = False
        if run_mode == RUN_MODE_METADATA_ONLY:
            run_metadata_only(
                name=name,
                output_dir=output_dir,
                existing_state=existing_state,
                runtime_settings=settings_snapshot,
                source_pdf_path=source_pdf_path,
                author=author,
                publication_year=publication_year,
                death_year=death_year,
            )
            return
        if run_mode == RUN_MODE_TRANSLATION_ONLY:
            run_translation_only(
                name=name,
                output_dir=output_dir,
                existing_state=existing_state,
                runtime_settings=settings_snapshot,
                translation_chunk_pages=translation_chunk_pages,
            )
            return
        if run_mode == RUN_MODE_KOREAN_PDF_ONLY:
            run_korean_pdf_only(
                name=name,
                output_dir=output_dir,
                existing_state=existing_state,
                runtime_settings=settings_snapshot,
            )
            return
        raise ValueError(f"Unsupported run mode: {run_mode}")

    force_rebuild_downstream = bool(retry_pages)
    translation_model_changed = existing_state.get("translation_model") != TRANSLATION_MODEL
    total_input_pages = get_pdf_page_count(input_pdf)
    images_dir = os.path.join(output_dir, "images")
    raw_pdf_metadata = extract_pdf_metadata(source_pdf_path)
    deterministic_metadata = {field: None for field in ("title", "author", "publication_year", "death_year")}
    ai_metadata = normalize_recorded_ai_metadata({})
    manual_override = load_metadata_override(output_dir, name)
    metadata_report_reused = False
    cached_metadata_report = load_metadata_report(output_dir, name) if resume and not force_refresh_metadata else {}
    if cached_metadata_report:
        raw_pdf_metadata = raw_pdf_metadata or (
            cached_metadata_report.get("raw_pdf_metadata")
            if isinstance(cached_metadata_report.get("raw_pdf_metadata"), dict)
            else {}
        )
        deterministic_metadata = (
            cached_metadata_report.get("deterministic_inference")
            if isinstance(cached_metadata_report.get("deterministic_inference"), dict)
            else deterministic_metadata
        )
        ai_metadata = normalize_recorded_ai_metadata(cached_metadata_report.get("ai_inference"))
        metadata_report_reused = True

    def refresh_metadata_report() -> tuple[dict, dict, dict, dict]:
        effective_metadata, effective_sources = build_effective_metadata(
            author,
            publication_year,
            death_year,
            raw_pdf_metadata,
            deterministic_metadata,
            ai_metadata,
        )
        rights_metadata, rights_sources = build_rights_metadata(
            author,
            publication_year,
            death_year,
            raw_pdf_metadata,
            deterministic_metadata,
            ai_metadata,
        )
        (
            effective_metadata,
            effective_sources,
            rights_metadata,
            rights_sources,
        ) = apply_manual_metadata_override(
            effective_metadata,
            effective_sources,
            rights_metadata,
            rights_sources,
            manual_override,
        )
        metadata_report = {
            "checked_at": datetime.now().isoformat(),
            "paper_name": name,
            "raw_pdf_metadata": raw_pdf_metadata,
            "deterministic_inference": deterministic_metadata,
            "ai_inference": ai_metadata,
            "manual_override": manual_override,
            "effective_metadata": effective_metadata,
            "effective_sources": effective_sources,
            "rights_metadata": rights_metadata,
            "rights_sources": rights_sources,
        }
        save_metadata_report(output_dir, name, metadata_report)
        return effective_metadata, effective_sources, rights_metadata, rights_sources

    effective_metadata, effective_sources, rights_metadata, rights_sources = refresh_metadata_report()
    if metadata_report_reused:
        print("\n[METADATA] Reusing cached metadata report.")
    if manual_override:
        print(
            "  [METADATA] Applying manual override fields: "
            + ", ".join(sorted(manual_override))
        )
    print("\n[RIGHTS] Running rights check heuristic...")
    meta_author = rights_metadata.get("author")
    meta_publication_year = rights_metadata.get("publication_year")
    meta_death_year = rights_metadata.get("death_year")

    rights_info = {
        "checked_at": datetime.now().isoformat(),
        **assess_rights(meta_author, meta_publication_year, meta_death_year),
    }
    rights_path = os.path.join(output_dir, f"{name}_rights_check.json")
    with open(rights_path, "w", encoding="utf-8") as f:
        json.dump(rights_info, f, ensure_ascii=False, indent=2)
    print(f"  Rights check saved: {rights_path}")
    print(f"  Assessment: {rights_info['assessment']} ({rights_info['reason']})")
    rights_context = build_rights_context(rights_info)

    # ?? STEP 0: PDF ??Images ????????????????????????????????????????????
    print("\n[STEP 0] Converting PDF to images...")
    page_numbers = None
    retry_page_numbers: set[int] = set()
    state_requested_pages = existing_state.get("requested_pages")
    if retry_pages:
        selected = parse_page_range(retry_pages, total_input_pages)
        page_numbers = selected
        retry_page_numbers = {page_idx + 1 for page_idx in selected}
        requested_page_numbers = [
            int(page)
            for page in (state_requested_pages or list(range(1, total_input_pages + 1)))
        ]
        print(f"  Total pages: {total_input_pages}")
        print(f"  Retrying pages: {[i + 1 for i in selected]}")
    elif pages:
        selected = parse_page_range(pages, total_input_pages)
        page_numbers = selected
        requested_page_numbers = [i + 1 for i in selected]
        print(f"  Total pages: {total_input_pages}")
        print(f"  Selected pages: {[i + 1 for i in selected]}")
    else:
        requested_page_numbers = list(range(1, total_input_pages + 1))
        print(f"  Total pages: {total_input_pages}")

    state = {
        "paper_name": name,
        "source_pdf": source_pdf_path,
        "input_pdf": os.path.abspath(input_pdf),
        "output_dir": os.path.abspath(output_dir),
        "stdout_log_path": pipeline_stdout_log_path(output_dir, name),
        "stderr_log_path": pipeline_stderr_log_path(output_dir, name),
        "requested_pages": requested_page_numbers,
        "last_rendered_pages": existing_state.get("last_rendered_pages", []),
        "pages_arg": pages,
        "retry_pages_arg": retry_pages,
        "author": author,
        "publication_year": publication_year,
        "death_year": death_year,
        "raw_pdf_metadata": raw_pdf_metadata,
        "metadata": effective_metadata,
        "metadata_sources": effective_sources,
        "rights_metadata": rights_metadata,
        "rights_metadata_sources": rights_sources,
        "workers": workers,
        "translation_chunk_pages": translation_chunk_pages,
        "translation_model": TRANSLATION_MODEL,
        "publish_enabled": publish_enabled,
        "force_refresh_images": force_refresh_images,
        "force_refresh_metadata": force_refresh_metadata,
        "runtime_settings": settings_snapshot,
        "metadata_override_path": (
            metadata_override_path(output_dir, name)
            if manual_override
            else None
        ),
        "layout_profile": existing_state.get("layout_profile"),
        "current_stage": "step0_images",
        "last_successful_stage": existing_state.get("last_successful_stage"),
        "last_error": None,
        "last_progress_at": datetime.now().isoformat(),
        "last_progress_note": "Preparing page images.",
        "checked_at": datetime.now().isoformat(),
        "failed_pages": existing_state.get("failed_pages", []),
        "failed_page_details": existing_state.get("failed_page_details", []),
        "successful_pages": existing_state.get("successful_pages", []),
    }
    save_pipeline_state(output_dir, name, state)

    image_paths = []
    if resume and not force_refresh_images:
        image_paths = collect_cached_image_paths(images_dir, requested_page_numbers)
        if image_paths:
            print("\n[STEP 0] Reusing cached page images...")
    images_reused = bool(image_paths)
    if not image_paths:
        image_paths = pdf_to_images(input_pdf, images_dir, page_numbers=page_numbers)
    if page_numbers is None:
        page_jobs = [(idx + 1, path) for idx, path in enumerate(image_paths)]
    else:
        page_jobs = [(page_idx + 1, path) for page_idx, path in zip(page_numbers, image_paths)]

    layout_profile = existing_state.get("layout_profile") if resume and not force_refresh_images else None
    if layout_profile:
        print("\n[LAYOUT] Reusing cached layout profile...")
    else:
        layout_profile = infer_source_layout_profile(source_pdf_path, image_paths, page_numbers)
    layout_profile_path = os.path.join(output_dir, f"{name}_layout_profile.json")
    with open(layout_profile_path, "w", encoding="utf-8") as f:
        json.dump(layout_profile, f, ensure_ascii=False, indent=2)
    if layout_profile:
        print(
            "\n[LAYOUT] Source profile: "
            f"{layout_profile['page_width_in']} x {layout_profile['page_height_in']} in, "
            f"{layout_profile['font_size_pt']}pt base text."
        )
        print(f"  Layout profile saved: {layout_profile_path}")
    image_progress_note = (
        "Reused cached page images."
        if images_reused
        else "Rendered page images."
    )
    state.update(
        {
            "last_rendered_pages": [page_num for page_num, _ in page_jobs],
            "layout_profile": layout_profile,
        }
    )
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="step1_2_transcription",
        last_successful_stage="step0_images",
        last_error=None,
        extra={"last_progress_note": image_progress_note},
    )

    num_pages = len(requested_page_numbers)

    # ?? STEP 1 & 2: Per-page structure analysis + LaTeX transcription ???
    all_transcription_notes = []
    failure_by_page = {
        int(item["page_number"]): item
        for item in existing_state.get("failed_page_details", [])
        if (
            isinstance(item, dict)
            and item.get("page_number") is not None
            and int(item["page_number"]) in requested_page_numbers
        )
    }

    def process_page(page_job: tuple[int, str]) -> tuple[int, str, str, str | None]:
        page_num, img_path = page_job
        struct_path = page_structure_path(output_dir, page_num)
        tex_path = page_tex_path(output_dir, page_num)

        if should_reuse_cached_page(
            resume=resume,
            page_num=page_num,
            retry_page_numbers=retry_page_numbers,
            struct_path=struct_path,
            tex_path=tex_path,
        ):
            with open(tex_path, encoding="utf-8") as f:
                latex_source = normalize_latex_source(f.read())
            with open(struct_path, encoding="utf-8") as f:
                structure_json = f.read()
            print(f"\n[STEP 1/2] Reusing cached page {page_num}/{num_pages}...")
            return page_num, latex_source, structure_json, None, True

        print(f"\n[STEP 1] Analyzing structure ??page {page_num}/{num_pages}...")
        structure_json = call_vision(STEP1_SYS, f"{rights_context}\n\n{STEP1_USR}", img_path)
        with open(struct_path, "w", encoding="utf-8") as f:
            f.write(structure_json)
        print(f"  Structure saved: {struct_path}")

        print(f"[STEP 2] Transcribing to LaTeX ??page {page_num}/{num_pages}...")
        step2_user = STEP2_USR.format(structure_analysis_json=structure_json)
        latex_source = None
        transcription_response = ""
        for attempt in range(1, 4):
            transcription_response = call_vision(
                STEP2_SYS,
                f"{rights_context}\n\n{step2_user}",
                img_path,
                max_tokens=16384,
            )
            candidate = extract_block(transcription_response, "BEGIN_LATEX")
            if not candidate:
                print(
                    f"  WARNING: Could not extract LaTeX for page {page_num} "
                    f"(attempt {attempt}/3)."
                )
                candidate = transcription_response
            candidate = normalize_latex_source(candidate)
            if is_latex_document(candidate):
                latex_source = candidate
                break
            print(
                f"  WARNING: Malformed LaTeX for page {page_num} "
                f"(attempt {attempt}/3). Retrying..."
            )
        if latex_source is None:
            raise RuntimeError(
                f"STEP 2 failed: malformed LaTeX on page {page_num} after 3 attempts."
            )
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex_source)
        print(f"  LaTeX saved: {tex_path}")
        notes = extract_block(transcription_response, "TRANSCRIPTION_NOTES")
        return page_num, latex_source, structure_json, notes, False

    def process_page_safe(page_job: tuple[int, str]) -> dict:
        page_num, img_path = page_job
        record_pipeline_progress(
            state,
            output_dir,
            name,
            f"Processing page {page_num}/{num_pages}.",
        )
        try:
            result_page, latex_source, structure_json, notes, reused_cache = process_page(page_job)
            failure_by_page.pop(page_num, None)
            failure_path = page_failure_path(output_dir, page_num)
            if os.path.exists(failure_path):
                os.remove(failure_path)
            return {
                "ok": True,
                "page_number": result_page,
                "latex_source": latex_source,
                "structure_json": structure_json,
                "notes": notes,
                "reused_cache": reused_cache,
            }
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            failure = {
                "page_number": page_num,
                "stage": "step1_2",
                "status": "failed",
                "error": message,
                "image_path": img_path,
                "structure_path": page_structure_path(output_dir, page_num),
                "tex_path": page_tex_path(output_dir, page_num),
                "updated_at": datetime.now().isoformat(),
            }
            failure_by_page[page_num] = failure
            with open(page_failure_path(output_dir, page_num), "w", encoding="utf-8") as f:
                json.dump(failure, f, ensure_ascii=False, indent=2)
            print(
                f"\n[STEP 1/2] WARNING: page {page_num}/{num_pages} failed and will be skipped."
            )
            print(f"  [STEP 1/2] Reason: {message}")
            return {"ok": False, "page_number": page_num, "failure": failure}

    successful_results = []
    if page_jobs:
        first_result = process_page_safe(page_jobs[0])
        if first_result["ok"]:
            successful_results.append(first_result)
            if first_result.get("notes"):
                all_transcription_notes.append(
                    f"--- Page {first_result['page_number']} ---\n{first_result['notes']}"
                )

    if successful_results:
        first_success = successful_results[0]
        if metadata_report_reused and first_success.get("reused_cache") and not force_refresh_metadata:
            print("\n[METADATA] Keeping cached metadata inference.")
        else:
            first_structure_json = first_success.get("structure_json") or ""
            first_page_latex = first_success.get("latex_source") or ""
            deterministic_metadata = infer_metadata_from_structure(first_structure_json)
            ai_metadata = infer_metadata_with_ai(
                name,
                raw_pdf_metadata,
                first_structure_json,
                first_page_latex,
            )
            effective_metadata, effective_sources, rights_metadata, rights_sources = refresh_metadata_report()
            state.update(
                {
                    "metadata": effective_metadata,
                    "metadata_sources": effective_sources,
                    "rights_metadata": rights_metadata,
                    "rights_metadata_sources": rights_sources,
                }
            )
            mark_pipeline_stage(
                state,
                output_dir,
                name,
                current_stage="step1_2_transcription",
                last_successful_stage="metadata",
            )
            print("\n[METADATA] Saved inferred metadata report.")
            if ai_metadata.get("status") == "ok":
                print(
                    "  [METADATA] AI fields: "
                    f"title={effective_metadata.get('title')!r}, "
                    f"author={effective_metadata.get('author')!r}, "
                    f"year={effective_metadata.get('publication_year')!r}"
                )
            elif ai_metadata.get("error"):
                print(f"  [METADATA] AI inference skipped: {ai_metadata['error']}")

            meta_author = rights_metadata.get("author")
            meta_publication_year = rights_metadata.get("publication_year")
            meta_death_year = rights_metadata.get("death_year")
            rights_info = {
                "checked_at": datetime.now().isoformat(),
                **assess_rights(meta_author, meta_publication_year, meta_death_year),
            }
            with open(rights_path, "w", encoding="utf-8") as f:
                json.dump(rights_info, f, ensure_ascii=False, indent=2)
            rights_context = build_rights_context(rights_info)
            print(
                "  [RIGHTS] Updated from effective metadata "
                f"(author source={rights_sources.get('author')}, "
                f"year source={rights_sources.get('publication_year')})."
            )
            print(
                f"  [RIGHTS] Assessment: {rights_info['assessment']} "
                f"({rights_info['reason']})"
            )

    remaining = page_jobs[1:]
    max_workers = max(1, min(workers, len(remaining))) if remaining else 1
    if remaining and max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_page_safe, item) for item in remaining]
            for future in as_completed(futures):
                result = future.result()
                if result["ok"]:
                    successful_results.append(result)
                    if result.get("notes"):
                        all_transcription_notes.append(
                            f"--- Page {result['page_number']} ---\n{result['notes']}"
                        )
    elif remaining:
        for item in remaining:
            result = process_page_safe(item)
            if result["ok"]:
                successful_results.append(result)
                if result.get("notes"):
                    all_transcription_notes.append(
                        f"--- Page {result['page_number']} ---\n{result['notes']}"
                    )

    successful_page_numbers = []
    page_latex_sources = []
    for page_num in requested_page_numbers:
        if not should_include_page_in_merge(page_num, failure_by_page):
            continue
        tex_path = page_tex_path(output_dir, page_num)
        if not os.path.exists(tex_path):
            continue
        with open(tex_path, encoding="utf-8") as f:
            source = normalize_latex_source(f.read())
        if not is_latex_document(source):
            failure = {
                "page_number": page_num,
                "stage": "step1_2",
                "status": "failed",
                "error": "Cached page TeX is malformed and cannot be merged.",
                "image_path": os.path.join(images_dir, f"page_{page_num:03d}.png"),
                "structure_path": page_structure_path(output_dir, page_num),
                "tex_path": tex_path,
                "updated_at": datetime.now().isoformat(),
            }
            failure_by_page[page_num] = failure
            with open(page_failure_path(output_dir, page_num), "w", encoding="utf-8") as f:
                json.dump(failure, f, ensure_ascii=False, indent=2)
            continue
        successful_page_numbers.append(page_num)
        page_latex_sources.append(source)

    failed_page_details = [failure_by_page[page] for page in sorted(failure_by_page)]
    failed_page_numbers = [item["page_number"] for item in failed_page_details]
    state.update(
        {
            "failed_pages": failed_page_numbers,
            "failed_page_details": failed_page_details,
            "successful_pages": successful_page_numbers,
            "checked_at": datetime.now().isoformat(),
        }
    )
    if (
        existing_state.get("successful_pages") != successful_page_numbers
        or existing_state.get("failed_pages") != failed_page_numbers
        or existing_state.get("layout_profile") != layout_profile
    ):
        force_rebuild_downstream = True
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="step3_digitalized_pdf",
        last_successful_stage="step1_2_transcription",
        last_error=(
            f"Failed pages remain: {failed_page_numbers}"
            if failed_page_numbers
            else None
        ),
        extra={"last_progress_note": "Compiling digitalized PDF."},
    )
    # Save transcription notes
    if all_transcription_notes:
        notes_path = os.path.join(output_dir, f"{name}_transcription_notes.txt")
        with open(notes_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(all_transcription_notes))

    if failed_page_numbers:
        print(
            f"\n[STEP 1/2] Partial success: skipped failed page(s) {failed_page_numbers} "
            "and continuing with completed pages."
        )
    if not page_latex_sources:
        raise RuntimeError(
            "No pages were successfully transcribed. Nothing to merge. "
            "Use the retry flow after fixing the model refusal/problem."
        )

    # ?? Merge pages ?????????????????????????????????????????????????????
    print(
        f"\n[MERGE] Merging {len(successful_page_numbers)} successful page(s) "
        f"out of {num_pages} requested..."
    )
    merged_latex = merge_pages(page_latex_sources)
    merged_latex = apply_source_layout_profile(merged_latex, layout_profile)
    if not is_latex_document(merged_latex):
        raise RuntimeError("Merged LaTeX is malformed. Aborting before compilation.")
    merged_tex_path = os.path.join(output_dir, f"{name}_merged.tex")
    with open(merged_tex_path, "w", encoding="utf-8") as f:
        f.write(merged_latex)
    print(f"  Merged LaTeX saved: {merged_tex_path}")

    # ?? STEP 3: Compile + auto-fix (pdflatex) ??????????????????????????
    final_dig_tex = os.path.join(output_dir, f"{name}_digitalized.tex")
    dig_pdf = os.path.join(output_dir, f"{name}_digitalized.pdf")
    dig_err_log = os.path.join(output_dir, f"{name}_digitalized_error.log")
    if (
        resume
        and not force_rebuild_downstream
        and os.path.exists(final_dig_tex)
        and os.path.exists(dig_pdf)
        and not os.path.exists(dig_err_log)
    ):
        print("\n[STEP 3] Reusing cached digitalized PDF/TeX...")
        with open(final_dig_tex, encoding="utf-8") as f:
            final_dig_latex = f.read()
        dig_ok = True
    else:
        if os.path.exists(dig_err_log):
            print("\n[STEP 3] Found previous error log; recompiling digitalized PDF...")
        print("\n[STEP 3] Compiling digitalized PDF (pdflatex)...")
        dig_ok, final_dig_latex, dig_pdf = auto_fix_loop(
            merged_latex,
            output_dir,
            f"{name}_digitalized",
            max_attempts=5,
            compiler="pdflatex",
            fix_system_prompt=STEP3_SYS,
            fix_user_template=STEP3_USR,
            double_compile=False,
        )

    # Save final digitalized LaTeX
    with open(final_dig_tex, "w", encoding="utf-8") as f:
        f.write(final_dig_latex)

    if dig_ok:
        print(f"  [STEP 4] Digitalized PDF: {dig_pdf}")
    else:
        print("  [STEP 4] WARNING: Digitalized PDF compilation failed.")
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="translation",
        last_successful_stage="digitalized_pdf" if dig_ok else None,
        last_error="Digitalized PDF compilation failed." if not dig_ok else None,
        extra={"last_progress_note": "Translating Korean LaTeX."},
    )

    # ?? STEP 5: Glossary ????????????????????????????????????????????????
    korean_tex_path = os.path.join(output_dir, f"{name}_Korean.tex")
    tnotes_path = os.path.join(output_dir, f"{name}_translation_notes.txt")
    translation_rebuilt = False
    if translation_model_changed:
        print(
            "\n[TRANSLATE] Translation model changed to "
            f"{TRANSLATION_MODEL}; regenerating Korean LaTeX..."
        )
    if (
        resume
        and not force_rebuild_downstream
        and not translation_model_changed
        and os.path.exists(korean_tex_path)
    ):
        print("\n[TRANSLATE] Reusing cached Korean LaTeX...")
        with open(korean_tex_path, encoding="utf-8") as f:
            korean_latex = f.read()
    else:
        print("\n[TRANSLATE] Translating to Korean...")
        print(f"  [TRANSLATE] Model: {TRANSLATION_MODEL}")
        korean_latex, notes_all = translate_digitalized_latex(
            final_dig_latex,
            translation_chunk_pages,
            progress_callback=lambda chunk_idx, total_chunks: record_pipeline_progress(
                state,
                output_dir,
                name,
                f"Translating chunk {chunk_idx}/{total_chunks}.",
            ),
        )
        with open(korean_tex_path, "w", encoding="utf-8") as f:
            f.write(korean_latex)
        if notes_all:
            with open(tnotes_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(notes_all))
        translation_rebuilt = True
    print(f"  Korean LaTeX saved: {korean_tex_path}")
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="korean_pdf",
        last_successful_stage="translation",
        extra={"last_progress_note": "Compiling Korean PDF."},
    )

    # ?? STEP 7: Compile Korean PDF (xelatex) + auto-fix ?????????????????
    kor_pdf = os.path.join(output_dir, f"{name}_Korean.pdf")
    kor_err_log = os.path.join(output_dir, f"{name}_Korean_error.log")
    if (
        resume
        and not force_rebuild_downstream
        and not translation_rebuilt
        and os.path.exists(kor_pdf)
        and not os.path.exists(kor_err_log)
    ):
        print("\n[KOREAN PDF] Reusing cached Korean PDF...")
        kor_ok = True
        final_kor_latex = korean_latex
    else:
        if os.path.exists(kor_err_log):
            print("\n[KOREAN PDF] Found previous error log; recompiling Korean PDF...")
        print("\n[KOREAN PDF] Compiling Korean PDF (xelatex)...")
        kor_ok, final_kor_latex, kor_pdf = auto_fix_loop(
            korean_latex,
            output_dir,
            f"{name}_Korean",
            max_attempts=5,
            compiler="xelatex",
            fix_system_prompt=STEP7_SYS,
            fix_user_template=STEP7_USR,
            double_compile=False,
        )

    # Save final Korean LaTeX
    with open(korean_tex_path, "w", encoding="utf-8") as f:
        f.write(final_kor_latex)

    if kor_ok:
        print(f"  Korean PDF: {kor_pdf}")
    else:
        print("  WARNING: Korean PDF compilation failed.")
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="report",
        last_successful_stage="korean_pdf" if kor_ok else None,
        last_error="Korean PDF compilation failed." if not kor_ok else None,
        extra={"last_progress_note": "Generating quality report."},
    )

    # ?? STEP 8: Quality report ??????????????????????????????????????????
    print("\n[REPORT] Generating quality report...")
    quality_report_path = finalize_report(
        name,
        num_pages,
        dig_ok,
        kor_ok,
        output_dir,
        successful_pages=len(successful_page_numbers),
        failed_pages=failed_page_numbers,
    )
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="publish",
        last_successful_stage="report",
        extra={
            "last_progress_note": (
                "Publishing bundle to Supabase."
                if publish_enabled
                else "Skipping publish step."
            )
        },
    )

    publish_report = {
        "status": "disabled",
        "reason": "Publishing disabled by configuration.",
        "slug": None,
        "published_at": None,
    }
    if publish_enabled:
        print("\n[PUBLISH] Publishing archive bundle...")
        try:
            publish_bundle = build_publish_bundle(
                output_dir=output_dir,
                name=name,
                source_pdf_path=source_pdf_path,
                requested_page_numbers=requested_page_numbers,
                successful_page_numbers=successful_page_numbers,
                effective_metadata=effective_metadata,
                rights_info=rights_info,
                raw_pdf_metadata=raw_pdf_metadata,
                deterministic_metadata=deterministic_metadata,
                ai_metadata=ai_metadata,
                layout_profile=layout_profile,
                final_dig_latex=final_dig_latex,
                final_kor_latex=final_kor_latex,
                manual_override=manual_override,
            )
            publish_report = publish_bundle_to_supabase(publish_bundle)
        except Exception as exc:
            publish_report = {
                "status": "failed",
                "reason": str(exc).strip() or exc.__class__.__name__,
                "slug": effective_metadata.get("title") or name,
                "published_at": None,
            }
        publish_report_path = save_publish_report(output_dir, name, publish_report)
        print(f"  [PUBLISH] Report saved: {publish_report_path}")
        print(
            f"  [PUBLISH] Status: {publish_report['status']}"
            + (f" ({publish_report['reason']})" if publish_report.get("reason") else "")
        )
    else:
        publish_report_path = save_publish_report(output_dir, name, publish_report)

    state.update(
        {
            "digitalized_compiled": dig_ok,
            "korean_compiled": kor_ok,
            "failed_pages": failed_page_numbers,
            "failed_page_details": failed_page_details,
            "successful_pages": successful_page_numbers,
            "quality_report_path": quality_report_path,
            "publish_report": publish_report,
            "publish_report_path": publish_report_path,
            "checked_at": datetime.now().isoformat(),
        }
    )
    mark_pipeline_stage(
        state,
        output_dir,
        name,
        current_stage="complete",
        last_successful_stage=(
            "publish"
            if publish_report.get("status") == "published"
            else "report"
        ),
        last_error=(
            publish_report.get("reason")
            if publish_report.get("status") == "failed"
            else None
        ),
        extra={
            "last_progress_note": (
                "Pipeline completed."
                if publish_report.get("status") != "failed"
                else "Pipeline completed with publish failure."
            )
        },
    )

    # ?? Summary ?????????????????????????????????????????????????????????
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Pages processed:    {num_pages}")
    print(f"  Pages merged:       {len(successful_page_numbers)}")
    if failed_page_numbers:
        print(f"  Failed pages:       {failed_page_numbers}")
    print(f"  Digitalized PDF:    {'OK' if dig_ok else 'FAILED'}")
    print(f"  Korean PDF:         {'OK' if kor_ok else 'FAILED'}")
    print(f"  Publish:            {publish_report['status'].upper()}")
    print(f"  Output directory:   {output_dir}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="PDF Digitization & Korean Translation Pipeline v2.0"
    )
    parser.add_argument("--input", required=False, help="Path to input PDF file (required for full runs)")
    parser.add_argument("--name", required=True, help="Paper name (used for output filenames)")
    parser.add_argument("--output", default="./output", help="Output directory (default: ./output)")
    parser.add_argument("--pages", default=None, help="Page range, e.g. '1-3' or '1,3,5'")
    parser.add_argument("--author", default=None, help="Author name for rights check log")
    parser.add_argument("--publication-year", type=int, default=None, help="Publication year for rights check log")
    parser.add_argument("--death-year", type=int, default=None, help="Author death year for rights check log")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers for page-level STEP 1/2")
    parser.add_argument("--no-resume", action="store_true", help="Disable cache/resume and recompute all steps")
    parser.add_argument("--translation-chunk-pages", type=int, default=4, help="Pages per translation chunk in STEP 6")
    parser.add_argument("--retry-pages", default=None, help="Retry only the given page range, e.g. '12' or '3,7'")
    parser.add_argument("--refresh-images", action="store_true", help="Force STEP 0 image rendering even when cached page PNGs exist")
    parser.add_argument("--refresh-metadata", action="store_true", help="Force metadata inference even when a cached metadata report exists")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--metadata-only",
        action="store_true",
        help="Reuse cached page outputs and rerun only metadata inference plus rights check",
    )
    mode_group.add_argument(
        "--translation-only",
        action="store_true",
        help="Reuse cached digitalized TeX and rebuild only Korean LaTeX",
    )
    mode_group.add_argument(
        "--korean-pdf-only",
        action="store_true",
        help="Reuse cached Korean TeX and rebuild only the Korean PDF plus quality report",
    )
    parser.add_argument("--publish", dest="publish_enabled", action="store_true", help="Publish results to Supabase after pipeline completion (default)")
    parser.add_argument("--no-publish", dest="publish_enabled", action="store_false", help="Skip the Supabase publish step")
    parser.set_defaults(publish_enabled=True)

    args = parser.parse_args()
    run_mode = resolve_run_mode(
        metadata_only=args.metadata_only,
        translation_only=args.translation_only,
        korean_pdf_only=args.korean_pdf_only,
    )

    if run_mode == RUN_MODE_FULL:
        if not args.input:
            parser.error("--input is required for a full pipeline run.")
        if not os.path.exists(args.input):
            print(f"Error: Input file not found: {args.input}")
            sys.exit(1)
    elif (args.pages or args.retry_pages):
        parser.error("--pages and --retry-pages are only valid for full pipeline runs.")

    with redirect_pipeline_output(
        args.output,
        args.name,
        stdout_stream=sys.stdout,
        stderr_stream=sys.stderr,
    ):
        run_pipeline(
            args.input,
            args.name,
            args.output,
            args.pages,
            args.author,
            args.publication_year,
            args.death_year,
            args.workers,
            not args.no_resume,
            args.translation_chunk_pages,
            args.retry_pages,
            args.publish_enabled if run_mode == RUN_MODE_FULL else False,
            run_mode,
            args.refresh_images,
            args.refresh_metadata,
        )


if __name__ == "__main__":
    main()


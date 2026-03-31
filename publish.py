"""
Publishing helpers for sending pipeline output to Supabase and powering the web UI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "scholar-archive")
PUBLISHABLE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".json", ".tex", ".txt"}
SKIP_EXTENSIONS = {".log", ".aux", ".out", ".toc"}
PIPELINE_VERSION = "scholar-archive-pipeline-v1"
PAGE_TEX_PATTERN = re.compile(r"page_(\d{3})\.tex$")
PAGE_STRUCTURE_PATTERN = re.compile(r"page_(\d{3})_structure\.json$")
PAGE_FAILURE_PATTERN = re.compile(r"page_(\d{3})_failure\.json$")


def publish_report_path(output_dir: str, name: str) -> str:
    return os.path.join(output_dir, f"{name}_publish_report.json")


def save_publish_report(output_dir: str, name: str, report: dict) -> str:
    path = publish_report_path(output_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path


def get_supabase_url() -> str | None:
    return os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")


def get_supabase_service_key() -> str | None:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SECRET_KEY")


def _ascii_normalize(value: str | None) -> str:
    if not value:
        return ""
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def slugify(value: str | None) -> str:
    original = (value or "").strip()
    text = _ascii_normalize(original).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[-\s]+", "-", text, flags=re.UNICODE).strip("-")
    if text:
        return text
    if original:
        return f"document-{hashlib.sha256(original.encode('utf-8')).hexdigest()[:12]}"
    return "untitled-document"


def normalize_sort_name(name: str | None) -> str | None:
    if not name:
        return None
    return re.sub(r"\s+", " ", name).strip().lower()


def century_label(publication_year: int | None) -> str | None:
    if publication_year is None or publication_year <= 0:
        return None
    century = ((publication_year - 1) // 100) + 1
    suffix = "th"
    if century % 100 not in {11, 12, 13}:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(century % 10, "th")
    return f"{century}{suffix} century"


def split_latex_into_page_docs(source: str) -> list[str]:
    begin = re.search(r"\\begin\{document\}", source)
    end = re.search(r"\\end\{document\}\s*$", source)
    if not begin or not end:
        return [source]
    preamble = source[: begin.end()]
    body = source[begin.end() : end.start()]
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\\newpage\s*\n", body) if chunk.strip()]
    if not chunks:
        return [source]
    return [f"{preamble}\n{chunk}\n\\end{{document}}" for chunk in chunks]


def extract_latex_body(source: str) -> str:
    begin = re.search(r"\\begin\{document\}", source)
    end = re.search(r"\\end\{document\}", source)
    if begin and end:
        return source[begin.end() : end.start()]
    return source


def latex_to_readable_text(source: str) -> str:
    body = extract_latex_body(source)
    body = re.sub(r"(?m)^\s*%.*$", "", body)
    body = body.replace("\\newpage", "\n\n")
    body = body.replace("\\\\", "\n")
    body = re.sub(r"\\(?:begin|end)\{[^}]+\}", "\n", body)
    body = re.sub(r"\\(?:textit|textbf|textsc|emph|underline|mbox|textrm|textsf|texttt)\{([^{}]*)\}", r"\1", body)
    body = re.sub(r"\\(?:section|subsection|subsubsection)\*?\{([^{}]*)\}", r"\n\1\n", body)
    body = re.sub(r"\\(?:noindent|indent|centering|small|footnotesize|normalsize|large|Large|LARGE|huge|Huge|vspace\*?|hspace\*?)\b(?:\{[^}]*\})?", " ", body)
    body = re.sub(r"\\(?:fancyhead|fancyfoot|renewcommand|geometry|pagestyle|setmainfont|setmainhangulfont|setmainhanjafont)\b.*", " ", body)
    body = re.sub(r"\\[A-Za-z@]+(?:\[[^\]]*\])?(?:\{[^{}]*\})?", " ", body)
    body = body.replace("{", " ").replace("}", " ")
    body = re.sub(r"\s+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = re.sub(r"[ \t]{2,}", " ", body)
    return body.strip()


def _clean_metadata_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_year(value: Any) -> int | None:
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


def infer_metadata_from_structure_json(structure_json: str) -> dict:
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

    return {
        "title": title,
        "author": author,
        "publication_year": publication_year,
        "death_year": None,
    }


def assess_rights(
    author: str | None,
    publication_year: int | None,
    death_year: int | None,
) -> dict:
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


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_type_for_path(relative_path: str, name: str) -> str:
    rel = relative_path.replace("\\", "/")
    lower = rel.lower()
    if lower == f"{name.lower()}_source.pdf":
        return "source_pdf"
    if lower == f"{name.lower()}_digitalized.pdf":
        return "digitalized_pdf"
    if lower == f"{name.lower()}_korean.pdf":
        return "korean_pdf"
    if lower == f"{name.lower()}_digitalized.tex":
        return "digitalized_tex"
    if lower == f"{name.lower()}_korean.tex":
        return "korean_tex"
    if lower == f"{name.lower()}_merged.tex":
        return "merged_tex"
    if lower == f"{name.lower()}_metadata.json":
        return "metadata"
    if lower == f"{name.lower()}_quality_report.json":
        return "quality_report"
    if lower == f"{name.lower()}_rights_check.json":
        return "rights_check"
    if lower == f"{name.lower()}_pipeline_state.json":
        return "pipeline_state"
    if lower == f"{name.lower()}_layout_profile.json":
        return "layout_profile"
    if lower == f"{name.lower()}_transcription_notes.txt":
        return "transcription_notes"
    if lower == f"{name.lower()}_translation_notes.txt":
        return "translation_notes"
    if rel.startswith("images/"):
        return "page_image"
    if re.fullmatch(r"page_\d{3}\.tex", rel):
        return "page_tex"
    if re.fullmatch(r"page_\d{3}_structure\.json", rel):
        return "page_structure"
    if re.fullmatch(r"page_\d{3}_failure\.json", rel):
        return "page_failure"
    return "artifact"


def _sanitize_storage_component(part: str) -> str:
    if part in {".", ".."}:
        return "part"
    path = Path(part)
    suffix = "".join(path.suffixes).lower()
    stem = part[: -len(suffix)] if suffix else part
    safe = _ascii_normalize(stem).strip().lower()
    safe = re.sub(r"[^\w\s-]", "", safe, flags=re.UNICODE)
    safe = re.sub(r"[-\s]+", "-", safe, flags=re.UNICODE).strip("-")
    if not safe:
        safe = f"file-{hashlib.sha256(part.encode('utf-8')).hexdigest()[:12]}"
    return f"{safe}{suffix}"


def storage_relative_path(relative_path: str, asset_type: str) -> str:
    canonical = {
        "source_pdf": "source.pdf",
        "digitalized_pdf": "digitalized.pdf",
        "korean_pdf": "korean.pdf",
        "digitalized_tex": "digitalized.tex",
        "korean_tex": "korean.tex",
        "merged_tex": "merged.tex",
        "metadata": "metadata.json",
        "quality_report": "quality_report.json",
        "rights_check": "rights_check.json",
        "pipeline_state": "pipeline_state.json",
        "layout_profile": "layout_profile.json",
        "transcription_notes": "transcription_notes.txt",
        "translation_notes": "translation_notes.txt",
    }
    if asset_type in canonical:
        return canonical[asset_type]

    rel = relative_path.replace("\\", "/")
    if asset_type == "page_image" and re.fullmatch(r"images/page_\d{3}\.(png|jpg|jpeg)", rel):
        return rel
    if asset_type == "page_tex" and PAGE_TEX_PATTERN.fullmatch(Path(rel).name):
        return Path(rel).name
    if asset_type == "page_structure" and PAGE_STRUCTURE_PATTERN.fullmatch(Path(rel).name):
        return Path(rel).name
    if asset_type == "page_failure" and PAGE_FAILURE_PATTERN.fullmatch(Path(rel).name):
        return Path(rel).name

    parts = [part for part in rel.split("/") if part]
    return "/".join(_sanitize_storage_component(part) for part in parts)


def collect_publishable_files(output_dir: str, name: str) -> list[dict]:
    base = Path(output_dir)
    entries: list[dict] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in SKIP_EXTENSIONS:
            continue
        if path.suffix.lower() not in PUBLISHABLE_EXTENSIONS:
            continue
        rel = path.relative_to(base).as_posix()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        entries.append(
            {
                "relative_path": rel,
                "local_path": str(path),
                "asset_type": asset_type_for_path(rel, name),
                "byte_size": path.stat().st_size,
                "mime_type": mime,
            }
        )
    return entries


def _load_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _discover_page_numbers(output_dir: Path) -> list[int]:
    page_numbers = []
    for path in sorted(output_dir.glob("page_*.tex")):
        match = PAGE_TEX_PATTERN.fullmatch(path.name)
        if match:
            page_numbers.append(int(match.group(1)))
    return page_numbers


def _discover_first_structure_metadata(output_dir: Path) -> dict:
    for path in sorted(output_dir.glob("page_*_structure.json")):
        match = PAGE_STRUCTURE_PATTERN.fullmatch(path.name)
        if not match:
            continue
        metadata = infer_metadata_from_structure_json(_load_text(path))
        if any(metadata.get(field) for field in ("title", "author", "publication_year")):
            return metadata
    return {field: None for field in ("title", "author", "publication_year", "death_year")}


def _coerce_page_numbers(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    page_numbers = []
    for value in values:
        try:
            page_number = int(value)
        except Exception:
            continue
        if page_number > 0:
            page_numbers.append(page_number)
    return sorted(set(page_numbers))


def _fallback_effective_metadata(
    name: str,
    raw_pdf_metadata: dict,
    deterministic_metadata: dict,
    rights_info: dict,
) -> dict:
    return {
        "title": raw_pdf_metadata.get("title") or deterministic_metadata.get("title") or name,
        "author": raw_pdf_metadata.get("author") or deterministic_metadata.get("author") or rights_info.get("author"),
        "publication_year": _coerce_year(
            deterministic_metadata.get("publication_year") or rights_info.get("publication_year")
        ),
        "death_year": _coerce_year(
            deterministic_metadata.get("death_year") or rights_info.get("death_year")
        ),
        "journal_or_book": None,
        "volume": None,
        "issue": None,
        "pages": None,
        "language": None,
        "doi": None,
    }


def build_publish_bundle_from_existing_output(*, output_dir: str, name: str) -> dict:
    base = Path(output_dir)
    source_pdf_path = base / f"{name}_source.pdf"
    digitalized_tex_path = base / f"{name}_digitalized.tex"
    korean_tex_path = base / f"{name}_Korean.tex"
    if not digitalized_tex_path.exists():
        raise FileNotFoundError(f"Missing digitalized TeX: {digitalized_tex_path}")
    if not korean_tex_path.exists():
        raise FileNotFoundError(f"Missing Korean TeX: {korean_tex_path}")

    metadata_report = _load_json_if_exists(base / f"{name}_metadata.json")
    pipeline_state = _load_json_if_exists(base / f"{name}_pipeline_state.json")
    rights_info = _load_json_if_exists(base / f"{name}_rights_check.json")
    layout_profile = _load_json_if_exists(base / f"{name}_layout_profile.json")

    source_pdf = str(source_pdf_path) if source_pdf_path.exists() else ""
    raw_pdf_metadata = metadata_report.get("raw_pdf_metadata") or (
        extract_pdf_metadata(source_pdf) if source_pdf else {}
    )
    deterministic_metadata = metadata_report.get("deterministic_inference") or _discover_first_structure_metadata(base)
    ai_metadata = metadata_report.get("ai_inference") or {}
    effective_metadata = metadata_report.get("effective_metadata") or _fallback_effective_metadata(
        name,
        raw_pdf_metadata,
        deterministic_metadata,
        rights_info,
    )

    if not rights_info:
        rights_info = assess_rights(
            effective_metadata.get("author"),
            effective_metadata.get("publication_year"),
            effective_metadata.get("death_year"),
        )

    successful_page_numbers = _coerce_page_numbers(pipeline_state.get("successful_pages"))
    if not successful_page_numbers:
        successful_page_numbers = _discover_page_numbers(base)

    requested_page_numbers = _coerce_page_numbers(pipeline_state.get("requested_pages"))
    if not requested_page_numbers:
        requested_page_numbers = successful_page_numbers[:]

    if not successful_page_numbers:
        raise RuntimeError("No page_XXX.tex files were found in the output directory.")

    return build_publish_bundle(
        output_dir=output_dir,
        name=name,
        source_pdf_path=source_pdf,
        requested_page_numbers=requested_page_numbers,
        successful_page_numbers=successful_page_numbers,
        effective_metadata=effective_metadata,
        rights_info=rights_info,
        raw_pdf_metadata=raw_pdf_metadata,
        deterministic_metadata=deterministic_metadata,
        ai_metadata=ai_metadata,
        layout_profile=layout_profile or None,
        final_dig_latex=_load_text(digitalized_tex_path),
        final_kor_latex=_load_text(korean_tex_path),
    )


def _page_asset_path(asset_index: dict[str, dict], relative_path: str) -> str | None:
    asset = asset_index.get(relative_path)
    return asset["storage_path"] if asset else None


def build_publish_bundle(
    *,
    output_dir: str,
    name: str,
    source_pdf_path: str,
    requested_page_numbers: list[int],
    successful_page_numbers: list[int],
    effective_metadata: dict,
    rights_info: dict,
    raw_pdf_metadata: dict,
    deterministic_metadata: dict,
    ai_metadata: dict,
    layout_profile: dict | None,
    final_dig_latex: str,
    final_kor_latex: str,
) -> dict:
    bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", DEFAULT_STORAGE_BUCKET)
    title = effective_metadata.get("title") or name
    publication_year = effective_metadata.get("publication_year")
    slug = slugify(title)
    storage_root = f"documents/{slug}"
    files = collect_publishable_files(output_dir, name)

    for item in files:
        item["storage_bucket"] = bucket
        item["storage_path"] = f"{storage_root}/{storage_relative_path(item['relative_path'], item['asset_type'])}"

    asset_index = {item["relative_path"]: item for item in files}
    dig_page_docs = split_latex_into_page_docs(final_dig_latex)
    kor_page_docs = split_latex_into_page_docs(final_kor_latex)

    page_rows = []
    for idx, page_num in enumerate(successful_page_numbers):
        rel_image = f"images/page_{page_num:03d}.png"
        rel_page_tex = f"page_{page_num:03d}.tex"
        rel_structure = f"page_{page_num:03d}_structure.json"
        dig_doc = dig_page_docs[idx] if idx < len(dig_page_docs) else ""
        kor_doc = kor_page_docs[idx] if idx < len(kor_page_docs) else ""
        page_rows.append(
            {
                "page_number": page_num,
                "image_path": _page_asset_path(asset_index, rel_image),
                "digitalized_tex_path": _page_asset_path(asset_index, rel_page_tex),
                "digitalized_text": latex_to_readable_text(dig_doc),
                "korean_text": latex_to_readable_text(kor_doc),
                "structure_json_path": _page_asset_path(asset_index, rel_structure),
            }
        )

    key_assets = {item["asset_type"]: item["storage_path"] for item in files if item["asset_type"] != "artifact"}
    first_image = page_rows[0]["image_path"] if page_rows else None
    source_hash = sha256_file(source_pdf_path) if os.path.exists(source_pdf_path) else None

    document = {
        "slug": slug,
        "title": title,
        "author_display": effective_metadata.get("author"),
        "publication_year": publication_year,
        "century_label": century_label(publication_year),
        "language": effective_metadata.get("language"),
        "journal_or_book": effective_metadata.get("journal_or_book"),
        "volume": effective_metadata.get("volume"),
        "issue": effective_metadata.get("issue"),
        "page_range": effective_metadata.get("pages"),
        "doi": effective_metadata.get("doi"),
        "summary": None,
        "pipeline_version": PIPELINE_VERSION,
        "published_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "status": "published",
        "storage_bucket": bucket,
        "source_pdf_path": key_assets.get("source_pdf"),
        "digitalized_pdf_path": key_assets.get("digitalized_pdf"),
        "korean_pdf_path": key_assets.get("korean_pdf"),
        "cover_image_path": first_image,
        "page_count": len(successful_page_numbers),
        "requested_page_count": len(requested_page_numbers),
        "rights_assessment": rights_info.get("assessment"),
        "source_hash": source_hash,
    }

    author_name = effective_metadata.get("author")
    author_row = None
    if author_name:
        author_row = {
            "display_name": author_name,
            "sort_name": normalize_sort_name(author_name),
            "birth_year": None,
            "death_year": effective_metadata.get("death_year"),
        }

    snapshot = {
        "raw_pdf_metadata": raw_pdf_metadata or {},
        "deterministic_metadata": deterministic_metadata or {},
        "ai_metadata": ai_metadata or {},
        "effective_metadata": effective_metadata or {},
        "rights_metadata": {
            "author": rights_info.get("author"),
            "publication_year": rights_info.get("publication_year"),
            "death_year": rights_info.get("death_year"),
            "assessment": rights_info.get("assessment"),
            "reason": rights_info.get("reason"),
        },
        "layout_profile": layout_profile or {},
    }

    return {
        "storage_bucket": bucket,
        "storage_root": storage_root,
        "document": document,
        "author": author_row,
        "pages": page_rows,
        "assets": files,
        "snapshot": snapshot,
    }


def _supabase_request(
    *,
    base_url: str,
    service_key: str,
    method: str,
    path: str,
    query: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    expect_json: bool = True,
) -> Any:
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    if query:
        url += "?" + parse.urlencode(query, doseq=True)
    request_headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    if headers:
        request_headers.update(headers)
    req = request.Request(url, method=method.upper(), headers=request_headers, data=body)
    try:
        with request.urlopen(req, timeout=120) as response:
            payload = response.read()
            if not expect_json:
                return payload
            if not payload:
                return None
            return json.loads(payload.decode("utf-8"))
    except error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase {method.upper()} {path} failed ({exc.code}): {message}") from exc


def _upload_asset(base_url: str, service_key: str, asset: dict) -> None:
    with open(asset["local_path"], "rb") as f:
        body = f.read()
    quoted_path = parse.quote(asset["storage_path"], safe="/")
    _supabase_request(
        base_url=base_url,
        service_key=service_key,
        method="POST",
        path=f"storage/v1/object/{asset['storage_bucket']}/{quoted_path}",
        headers={
            "Content-Type": asset["mime_type"],
            "x-upsert": "true",
        },
        body=body,
        expect_json=True,
    )


def _ensure_storage_bucket(base_url: str, service_key: str, bucket: str) -> None:
    try:
        _supabase_request(
            base_url=base_url,
            service_key=service_key,
            method="POST",
            path="storage/v1/bucket",
            headers={"Content-Type": "application/json"},
            body=json.dumps(
                {
                    "id": bucket,
                    "name": bucket,
                    "public": True,
                }
            ).encode("utf-8"),
            expect_json=True,
        )
    except RuntimeError as exc:
        message = str(exc)
        if "Duplicate" in message or "already exists" in message or "(409)" in message:
            return
        raise


def _upsert_rows(
    base_url: str,
    service_key: str,
    table: str,
    rows: list[dict],
    on_conflict: str,
) -> list[dict]:
    if not rows:
        return []
    response = _supabase_request(
        base_url=base_url,
        service_key=service_key,
        method="POST",
        path=f"rest/v1/{table}",
        query={"on_conflict": on_conflict},
        headers={
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        },
        body=json.dumps(rows, ensure_ascii=False).encode("utf-8"),
        expect_json=True,
    )
    return response or []


def _delete_rows(base_url: str, service_key: str, table: str, filters: dict[str, str]) -> None:
    _supabase_request(
        base_url=base_url,
        service_key=service_key,
        method="DELETE",
        path=f"rest/v1/{table}",
        query=filters,
        headers={"Prefer": "return=minimal"},
        expect_json=False,
    )


def publish_bundle_to_supabase(bundle: dict) -> dict:
    base_url = get_supabase_url()
    service_key = get_supabase_service_key()
    if not base_url or not service_key:
        return {
            "status": "skipped",
            "reason": (
                "Supabase credentials are missing. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY."
            ),
            "slug": bundle["document"]["slug"],
            "published_at": None,
        }

    _ensure_storage_bucket(base_url, service_key, bundle["storage_bucket"])

    for asset in bundle["assets"]:
        _upload_asset(base_url, service_key, asset)

    document_rows = _upsert_rows(base_url, service_key, "documents", [bundle["document"]], "slug")
    if not document_rows:
        raise RuntimeError("Supabase did not return the upserted document row.")
    document = document_rows[0]
    document_id = document["id"]

    for table in ("document_pages", "document_assets", "document_metadata_snapshots", "document_authors"):
        _delete_rows(base_url, service_key, table, {"document_id": f"eq.{document_id}"})

    if bundle.get("author") and bundle["author"].get("sort_name"):
        author_rows = _upsert_rows(base_url, service_key, "authors", [bundle["author"]], "sort_name")
        if author_rows:
            _upsert_rows(
                base_url,
                service_key,
                "document_authors",
                [
                    {
                        "document_id": document_id,
                        "author_id": author_rows[0]["id"],
                        "ordinal": 1,
                    }
                ],
                "document_id,author_id",
            )

    page_rows = [{**row, "document_id": document_id} for row in bundle["pages"]]
    _upsert_rows(base_url, service_key, "document_pages", page_rows, "document_id,page_number")

    asset_rows = [
        {
            "document_id": document_id,
            "asset_type": asset["asset_type"],
            "storage_bucket": asset["storage_bucket"],
            "storage_path": asset["storage_path"],
            "mime_type": asset["mime_type"],
            "byte_size": asset["byte_size"],
        }
        for asset in bundle["assets"]
    ]
    _upsert_rows(base_url, service_key, "document_assets", asset_rows, "document_id,storage_path")

    snapshot_row = {
        "document_id": document_id,
        **bundle["snapshot"],
        "updated_at": datetime.now().isoformat(),
    }
    _upsert_rows(base_url, service_key, "document_metadata_snapshots", [snapshot_row], "document_id")

    return {
        "status": "published",
        "reason": None,
        "document_id": document_id,
        "slug": document["slug"],
        "storage_bucket": bundle["storage_bucket"],
        "storage_root": bundle["storage_root"],
        "uploaded_assets": len(bundle["assets"]),
        "published_pages": len(bundle["pages"]),
        "published_at": datetime.now().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish an existing Scholar Archive output directory to Supabase."
    )
    parser.add_argument("--output-dir", required=True, help="Existing pipeline output directory")
    parser.add_argument("--name", required=True, help="Document name prefix used in output filenames")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the publish bundle and write a report without uploading anything",
    )
    args = parser.parse_args()

    try:
        bundle = build_publish_bundle_from_existing_output(
            output_dir=args.output_dir,
            name=args.name,
        )
        if args.dry_run:
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
        else:
            report = publish_bundle_to_supabase(bundle)
    except Exception as exc:
        report = {
            "status": "failed",
            "reason": str(exc).strip() or exc.__class__.__name__,
            "slug": None,
            "published_at": None,
        }

    report_path = save_publish_report(args.output_dir, args.name, report)
    print(f"Publish report saved: {report_path}")
    print(f"Status: {report['status']}")
    if report.get("slug"):
        print(f"Slug: {report['slug']}")
    if report.get("reason"):
        print(f"Reason: {report['reason']}")

    if report["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

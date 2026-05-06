"""
Core pipeline functions for PDF digitization & Korean translation.
"""

import base64
import json
import os
import re
import shutil
from statistics import median
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

from google import genai
from google.genai import types

from backend.prompts import STEP3_SYS, STEP3_USR

# Model to use for all API calls — override via environment variable MODEL_NAME
DEFAULT_MODEL = os.environ.get("MODEL_NAME", "gemini-3-flash-preview")
TRANSLATION_MODEL = (
    os.environ.get("TRANSLATION_MODEL_NAME")
    or os.environ.get("GEMINI_TRANSLATION_MODEL")
    or "gemini-3.1-pro-preview"
)
API_TIMEOUT_SEC = int(os.environ.get("API_TIMEOUT_SEC", "180"))
API_RETRY_ATTEMPTS = max(1, int(os.environ.get("API_RETRY_ATTEMPTS", "2")))
# genai.Client is thread-safe per Google GenAI Python SDK documentation.
# pipeline.py uses ThreadPoolExecutor for page-level calls; all threads share
# this single client instance.
_GENAI_CLIENT: genai.Client | None = None


def _request_http_options() -> types.HttpOptions:
    """Build per-request HTTP options with explicit timeout and bounded retries."""
    return types.HttpOptions(
        timeout=API_TIMEOUT_SEC * 1000,
        retryOptions=types.HttpRetryOptions(
            attempts=API_RETRY_ATTEMPTS,
            initialDelay=1.0,
            maxDelay=5.0,
            expBase=2.0,
            jitter=0.2,
            httpStatusCodes=[429, 500, 502, 503, 504],
        ),
    )


def _latex_compile_timeout_sec() -> int:
    """Return the LaTeX compiler timeout in seconds."""
    return max(30, int(os.environ.get("LATEX_COMPILE_TIMEOUT_SEC", "120")))


def _ensure_genai_configured() -> genai.Client:
    """Create a GenAI client once and reuse it."""
    global _GENAI_CLIENT
    if _GENAI_CLIENT is not None:
        return _GENAI_CLIENT
    api_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GOOGLE_GEMINI_API_KEY")
    )
    if api_key:
        _GENAI_CLIENT = genai.Client(api_key=api_key)
    else:
        # Allow Vertex AI env-based configuration if present.
        _GENAI_CLIENT = genai.Client()
    return _GENAI_CLIENT


def _block_none_safety_settings():
    """Return safety settings with BLOCK_NONE across categories."""
    return [
        types.SafetySetting(
            category="HARM_CATEGORY_HARASSMENT",
            threshold="BLOCK_NONE",
        ),
        types.SafetySetting(
            category="HARM_CATEGORY_HATE_SPEECH",
            threshold="BLOCK_NONE",
        ),
        types.SafetySetting(
            category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
            threshold="BLOCK_NONE",
        ),
        types.SafetySetting(
            category="HARM_CATEGORY_DANGEROUS_CONTENT",
            threshold="BLOCK_NONE",
        ),
    ]


def _find_poppler_path() -> str | None:
    """Auto-detect poppler bin directory on Windows."""
    if shutil.which("pdftoppm"):
        return None  # already on PATH
    candidates = [
        os.path.expanduser("~/poppler/poppler-24.08.0/Library/bin"),
        os.path.expanduser("~/poppler/Library/bin"),
        "C:/poppler/poppler-24.08.0/Library/bin",
    ]
    for p in candidates:
        if os.path.isfile(os.path.join(p, "pdftoppm.exe")) or os.path.isfile(os.path.join(p, "pdftoppm")):
            return p
    return None


def _ensure_latex_on_path():
    """Add MiKTeX to PATH if not already there."""
    if shutil.which("pdflatex"):
        return
    miktex_bin = os.path.expanduser("~/AppData/Local/Programs/MiKTeX/miktex/bin/x64")
    if os.path.isdir(miktex_bin):
        os.environ["PATH"] = miktex_bin + os.pathsep + os.environ.get("PATH", "")


def _check_genai_prereqs() -> dict:
    key_names = (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GEMINI_API_KEY",
    )
    for key_name in key_names:
        if os.environ.get(key_name):
            return {
                "name": "genai",
                "status": "ok",
                "message": f"Using credentials from {key_name}.",
            }

    vertex_hints = [
        name
        for name in (
            "GOOGLE_GENAI_USE_VERTEXAI",
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_CLOUD_LOCATION",
            "GCP_PROJECT",
        )
        if os.environ.get(name)
    ]
    if vertex_hints:
        return {
            "name": "genai",
            "status": "warn",
            "message": (
                "No Gemini API key found; relying on Google Cloud/Vertex-style ambient "
                f"configuration ({', '.join(vertex_hints)})."
            ),
        }

    return {
        "name": "genai",
        "status": "warn",
        "message": (
            "No explicit Gemini credentials detected. Model calls may fail unless ambient "
            "Google credentials are configured."
        ),
    }


def _check_pdf_prereqs() -> dict:
    fitz_ok = False
    pdf2image_ok = False
    try:
        import fitz  # noqa: F401
        fitz_ok = True
    except Exception:
        pass

    try:
        import pdf2image  # noqa: F401
        pdf2image_ok = True
    except Exception:
        pass

    poppler_ready = bool(shutil.which("pdftoppm") or _find_poppler_path())
    if fitz_ok:
        return {
            "name": "pdf",
            "status": "ok",
            "message": "PyMuPDF available for PDF page counting and rendering fallback.",
        }
    if pdf2image_ok and poppler_ready:
        return {
            "name": "pdf",
            "status": "ok",
            "message": "pdf2image available with Poppler.",
        }
    return {
        "name": "pdf",
        "status": "error",
        "message": (
            "No working PDF rendering backend found. Install PyMuPDF, or install "
            "pdf2image with Poppler/pdftoppm on PATH."
        ),
    }


def _check_latex_prereqs(required_compilers: tuple[str, ...] = ("pdflatex", "xelatex")) -> dict:
    _ensure_latex_on_path()
    available = {
        "pdflatex": shutil.which("pdflatex"),
        "xelatex": shutil.which("xelatex"),
    }
    missing = []
    for compiler in required_compilers:
        if not available.get(compiler):
            missing.append(compiler)
    if missing:
        return {
            "name": "latex",
            "status": "error",
            "message": (
                "Missing required LaTeX compiler(s): "
                + ", ".join(missing)
                + ". Install MiKTeX/TeX Live and ensure they are on PATH."
            ),
        }
    return {
        "name": "latex",
        "status": "ok",
        "message": ", ".join(required_compilers) + " detected.",
    }


def run_preflight_checks(
    *,
    needs_genai: bool = True,
    needs_pdf: bool = True,
    latex_compilers: tuple[str, ...] = ("pdflatex", "xelatex"),
) -> dict:
    """Collect lightweight environment checks before long pipeline work starts."""
    checks = []
    if needs_genai:
        checks.append(_check_genai_prereqs())
    if needs_pdf:
        checks.append(_check_pdf_prereqs())
    if latex_compilers:
        checks.append(_check_latex_prereqs(required_compilers=latex_compilers))
    ok = not any(check["status"] == "error" for check in checks)
    return {"ok": ok, "checks": checks}


def get_pdf_page_count(pdf_path: str) -> int:
    """Return total page count without rendering all pages."""
    import fitz

    doc = fitz.open(pdf_path)
    count = doc.page_count
    doc.close()
    return count


def get_pdf_page_sizes(
    pdf_path: str,
    page_numbers: list[int] | None = None,
) -> list[tuple[float, float]]:
    """Return page sizes in PDF big points (1/72 inch)."""
    import fitz

    doc = fitz.open(pdf_path)
    if page_numbers is None:
        indices = range(doc.page_count)
    else:
        indices = [idx for idx in page_numbers if 0 <= idx < doc.page_count]

    sizes = []
    for idx in indices:
        rect = doc.load_page(idx).rect
        sizes.append((float(rect.width), float(rect.height)))
    doc.close()
    return sizes


def _sample_evenly(items: list[str], max_samples: int = 5) -> list[str]:
    """Return up to max_samples items spaced across the list."""
    if len(items) <= max_samples:
        return items
    if max_samples <= 1:
        return [items[0]]
    last = len(items) - 1
    indices = sorted({round(i * last / (max_samples - 1)) for i in range(max_samples)})
    return [items[idx] for idx in indices]


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _estimate_margin_fractions_from_image(image_path: str) -> dict[str, float] | None:
    """Estimate the dominant content box margins from a scanned page image."""
    try:
        from PIL import Image
    except Exception:
        return None

    try:
        with Image.open(image_path) as img:
            gray = img.convert("L")
            gray.thumbnail((600, 800))
            width, height = gray.size
            pixels = gray.load()
    except Exception:
        return None

    row_threshold = max(6, int(width * 0.02))
    col_threshold = max(6, int(height * 0.02))
    dark_threshold = 215

    row_counts: list[int] = []
    col_counts = [0] * width
    for y in range(height):
        row_count = 0
        for x in range(width):
            is_dark = pixels[x, y] < dark_threshold
            if is_dark:
                row_count += 1
                col_counts[x] += 1
        row_counts.append(row_count)

    top = next((idx for idx, count in enumerate(row_counts) if count >= row_threshold), None)
    left = next((idx for idx, count in enumerate(col_counts) if count >= col_threshold), None)
    if top is None or left is None:
        return None

    bottom_offset = next(
        (idx for idx, count in enumerate(reversed(row_counts)) if count >= row_threshold),
        None,
    )
    right_offset = next(
        (idx for idx, count in enumerate(reversed(col_counts)) if count >= col_threshold),
        None,
    )
    if bottom_offset is None or right_offset is None:
        return None

    bottom = height - 1 - bottom_offset
    right = width - 1 - right_offset
    return {
        "left": left / width,
        "right": (width - right - 1) / width,
        "top": top / height,
        "bottom": (height - bottom - 1) / height,
    }


def _format_tex_length(value: float, unit: str = "bp") -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}{unit}"


def infer_source_layout_profile(
    pdf_path: str,
    image_paths: list[str],
    page_numbers: list[int] | None = None,
) -> dict:
    """Infer a source-faithful page size and margin profile for historical scans."""
    page_sizes = get_pdf_page_sizes(pdf_path, page_numbers)
    if not page_sizes:
        return {}

    width_bp = round(median(width for width, _ in page_sizes), 2)
    height_bp = round(median(height for _, height in page_sizes), 2)
    width_in = width_bp / 72.0
    height_in = height_bp / 72.0

    margin_samples = [
        sample
        for sample in (
            _estimate_margin_fractions_from_image(path) for path in _sample_evenly(image_paths)
        )
        if sample
    ]

    default_fractions = {
        "left": 0.13,
        "right": 0.13,
        "top": 0.09,
        "bottom": 0.09,
    }
    if margin_samples:
        margin_fractions = {
            "left": round(
                _clamp(median(sample["left"] for sample in margin_samples), 0.08, 0.17),
                4,
            ),
            "right": round(
                _clamp(median(sample["right"] for sample in margin_samples), 0.08, 0.17),
                4,
            ),
            "top": round(
                _clamp(median(sample["top"] for sample in margin_samples), 0.05, 0.12),
                4,
            ),
            "bottom": round(
                _clamp(median(sample["bottom"] for sample in margin_samples), 0.05, 0.12),
                4,
            ),
        }
    else:
        margin_fractions = default_fractions

    font_size_pt = 10
    if width_in <= 5.9 and height_in <= 8.6:
        font_size_pt = 12
    elif width_in <= 6.4 or height_in <= 9.2:
        font_size_pt = 11

    margins_bp = {
        side: round(
            {
                "left": width_bp,
                "right": width_bp,
                "top": height_bp,
                "bottom": height_bp,
            }[side]
            * fraction,
            2,
        )
        for side, fraction in margin_fractions.items()
    }
    geometry_options = ",".join(
        [
            f"paperwidth={_format_tex_length(width_bp)}",
            f"paperheight={_format_tex_length(height_bp)}",
            f"top={_format_tex_length(margins_bp['top'])}",
            f"bottom={_format_tex_length(margins_bp['bottom'])}",
            f"left={_format_tex_length(margins_bp['left'])}",
            f"right={_format_tex_length(margins_bp['right'])}",
            "headheight=14pt",
        ]
    )

    return {
        "profile_version": 1,
        "paperwidth_bp": width_bp,
        "paperheight_bp": height_bp,
        "page_width_in": round(width_in, 2),
        "page_height_in": round(height_in, 2),
        "font_size_pt": font_size_pt,
        "margin_fractions": margin_fractions,
        "margins_bp": margins_bp,
        "geometry_options": geometry_options,
        "sampled_image_count": len(margin_samples),
        "strategy": "source_page_size_with_historical_margin_heuristic",
    }


def pdf_to_images(
    pdf_path: str,
    output_dir: str,
    dpi: int = 400,
    page_numbers: list[int] | None = None,
) -> list[str]:
    """STEP 0: Convert PDF pages to PNG images.

    page_numbers is 0-based and, if provided, only those pages are rendered.
    """
    from pdf2image import convert_from_path
    from pdf2image.exceptions import PDFInfoNotInstalledError

    os.makedirs(output_dir, exist_ok=True)
    if page_numbers is not None:
        # Render only selected pages via PyMuPDF (fast for sparse pages).
        import fitz

        selected = [p for p in page_numbers if p >= 0]
        if not selected:
            return []
        doc = fitz.open(pdf_path)
        scale = dpi / 72.0
        mat = fitz.Matrix(scale, scale)
        paths = []
        for page_idx in selected:
            if page_idx >= doc.page_count:
                continue
            page = doc.load_page(page_idx)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            p = os.path.join(output_dir, f"page_{page_idx+1:03d}.png")
            pix.save(p)
            paths.append(p)
            print(
                f"  [STEP 0] Saved page {page_idx+1}/{doc.page_count}: {p} (pymupdf)"
            )
        doc.close()
        return paths

    poppler_path = _find_poppler_path()
    kwargs = {"poppler_path": poppler_path} if poppler_path else {}
    try:
        images = convert_from_path(pdf_path, dpi=dpi, **kwargs)
        paths = []
        for i, img in enumerate(images):
            p = os.path.join(output_dir, f"page_{i+1:03d}.png")
            img.save(p, "PNG")
            paths.append(p)
            print(f"  [STEP 0] Saved page {i+1}/{len(images)}: {p}")
        return paths
    except PDFInfoNotInstalledError:
        # Fallback for environments without Poppler: render via PyMuPDF.
        import fitz

        doc = fitz.open(pdf_path)
        scale = dpi / 72.0
        mat = fitz.Matrix(scale, scale)
        paths = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat, alpha=False)
            p = os.path.join(output_dir, f"page_{i+1:03d}.png")
            pix.save(p)
            paths.append(p)
            print(f"  [STEP 0] Saved page {i+1}/{len(doc)}: {p} (pymupdf)")
        doc.close()
        return paths


def image_to_base64(path: str) -> str:
    """Read an image file and return its base64-encoded string."""
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _media_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
        ext.lstrip("."), "image/png"
    )


def _extract_text(response) -> str:
    """Best-effort text extraction from GenAI response."""
    try:
        if hasattr(response, "text") and response.text:
            return response.text
    except Exception:
        pass

    try:
        candidate = response.candidates[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        if str(finish_reason) == "FinishReason.RECITATION":
            raise RuntimeError(
                "Gemini blocked output (finish_reason=RECITATION: potential copyrighted recitation). "
                "This pipeline asks for near-verbatim transcription, so this can happen. "
                "Try another model/provider or use a non-verbatim OCR path."
            )
    except RuntimeError:
        raise
    except Exception:
        pass

    try:
        parts = response.candidates[0].content.parts
        return "".join(getattr(p, "text", "") for p in parts).strip()
    except Exception:
        return ""


def call_vision(
    sys_prompt: str, user_prompt: str, img_path: str, max_tokens: int = 8192
) -> str:
    """Call Gemini with an image + text prompt."""
    client = _ensure_genai_configured()
    with open(img_path, "rb") as f:
        img_part = types.Part.from_bytes(
            data=f.read(),
            mime_type=_media_type(img_path),
        )
    resp = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=[user_prompt, img_part],
        config=types.GenerateContentConfig(
            system_instruction=sys_prompt,
            max_output_tokens=max_tokens,
            safety_settings=_block_none_safety_settings(),
            httpOptions=_request_http_options(),
        ),
    )
    return _extract_text(resp)


def call_text(
    sys_prompt: str,
    user_prompt: str,
    max_tokens: int = 8192,
    model: str | None = None,
) -> str:
    """Call Gemini text API (no image)."""
    client = _ensure_genai_configured()
    resp = client.models.generate_content(
        model=model or DEFAULT_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=sys_prompt,
            max_output_tokens=max_tokens,
            safety_settings=_block_none_safety_settings(),
            httpOptions=_request_http_options(),
        ),
    )
    return _extract_text(resp)


def extract_block(text: str, tag: str) -> str | None:
    """Extract content between %%% TAG %%% and %%% END_TAG %%% markers.

    Handles both patterns:
      %%% BEGIN_LATEX %%% ... %%% END_LATEX %%%
      %%% CORRECTED_LATEX %%% ... %%% END_CORRECTED_LATEX %%%
    """
    # Derive end tag: BEGIN_X -> END_X, otherwise END_TAG
    if tag.startswith("BEGIN_"):
        end_tag = "END_" + tag[len("BEGIN_"):]
    else:
        end_tag = "END_" + tag
    pattern = rf"%%%\s*{re.escape(tag)}\s*%%%(.*?)%%%\s*{re.escape(end_tag)}\s*%%%"
    m = re.search(pattern, text, re.DOTALL)
    if m:
        return m.group(1).strip()

    # Fallback: BEGIN tag exists but END tag is missing (truncated response).
    begin_pattern = rf"%%%\s*{re.escape(tag)}\s*%%%"
    b = re.search(begin_pattern, text, re.DOTALL)
    if b:
        return text[b.end():].strip()

    # Fallback: fenced LaTeX block.
    fence = re.search(r"```(?:latex)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return None


def normalize_latex_source(text: str) -> str:
    """Normalize model output into a compilable LaTeX document when possible."""
    src = text.strip()
    src = re.sub(r"^%%%\s*BEGIN_[A-Z_]+\s*%%%[\r\n]*", "", src)
    src = re.sub(r"[\r\n]*%%%\s*END_[A-Z_]+\s*%%%$", "", src)
    src = re.sub(r"^```(?:latex)?\s*", "", src, flags=re.IGNORECASE)
    src = re.sub(r"\s*```$", "", src)
    if "\\begin{document}" in src and "\\end{document}" not in src:
        src += "\n\n\\end{document}\n"
    return src


_FOOTNOTE_SYMBOL_INDEX = {
    "*": "1",
    "†": "2",
    "‡": "3",
    "§": "4",
    r"\dagger": "2",
    r"\ddagger": "3",
    r"\S": "4",
}


def _insert_before_document(source: str, snippet: str) -> str:
    """Insert a preamble snippet once, immediately before \\begin{document}."""
    if snippet in source:
        return source
    if "\\begin{document}" in source:
        return source.replace("\\begin{document}", f"{snippet}\n\\begin{{document}}", 1)
    return f"{source.rstrip()}\n{snippet}\n"


def _normalize_symbolic_footnotes(source: str) -> str:
    """Replace symbolic footnote optional args with numeric indices for footmisc."""
    pattern = re.compile(
        r"\\(footnote|footnotemark|footnotetext)\s*\[(\*|†|‡|§|\\dagger|\\ddagger|\\S)\]"
    )

    def repl(match: re.Match[str]) -> str:
        command = match.group(1)
        symbol = match.group(2)
        return f"\\{command}[{_FOOTNOTE_SYMBOL_INDEX[symbol]}]"

    return pattern.sub(repl, source)


def _normalize_decimal_cdots_in_text(source: str) -> str:
    """Wrap decimal middle dots in math mode when models emit them in text."""
    return re.sub(r"(?<!\$)(\d)\\cdot(?=\d)", r"\1$\\cdot$", source)


def _has_package(source: str, package: str) -> bool:
    return bool(
        re.search(
            rf"\\usepackage(?:\[[^\]]*\])?\{{[^}}]*\b{re.escape(package)}\b[^}}]*\}}",
            source,
        )
    )


def _ensure_graphicx_for_box_commands(source: str) -> str:
    """Load graphicx when scaling or image commands are present."""
    if _has_package(source, "graphicx"):
        return source
    if not re.search(r"\\(?:includegraphics|scalebox|resizebox|rotatebox|reflectbox)\b", source):
        return source
    return _insert_before_document(source, "\\usepackage{graphicx}")


def _ensure_wrapfig_for_wrapped_floats(source: str) -> str:
    """Load wrapfig when wrapfigure or wraptable environments are present."""
    if _has_package(source, "wrapfig"):
        return source
    if "\\begin{wrapfigure}" not in source and "\\begin{wraptable}" not in source:
        return source
    return _insert_before_document(source, "\\usepackage{wrapfig}")


def _ensure_tikz_for_tikzpicture(source: str) -> str:
    """Load TikZ when tikzpicture environments are present."""
    if _has_package(source, "tikz"):
        return source
    if "\\begin{tikzpicture}" not in source:
        return source
    return _insert_before_document(source, "\\usepackage{tikz}")


def _ensure_amsmath_for_math_constructs(source: str) -> str:
    """Load amsmath when translated math uses environments/macros it defines."""
    if _has_package(source, "amsmath"):
        return source
    if not re.search(
        r"\\(?:begin\{(?:align\*?|gather\*?|multline\*?|cases|split|aligned|gathered)\}"
        r"|text\b|dfrac\b|tfrac\b|eqref\b|tag\b|substack\b|overset\b|underset\b"
        r"|xrightarrow\b|xleftarrow\b|operatorname\b|boxed\b)",
        source,
    ):
        return source
    return _insert_before_document(source, "\\usepackage{amsmath}")


def _ensure_amssymb_for_math_symbols(source: str) -> str:
    """Load amssymb when translated math emits AMS symbol/font macros."""
    if _has_package(source, "amssymb"):
        return source
    if not re.search(
        r"\\(?:mathbb\b|mathfrak\b|therefore\b|because\b|square\b|blacksquare\b"
        r"|triangleq\b|lesssim\b|gtrsim\b|leqslant\b|geqslant\b|varnothing\b)",
        source,
    ):
        return source
    return _insert_before_document(source, "\\usepackage{amssymb}")


def _ensure_mathrsfs_for_mathscr(source: str) -> str:
    """Load mathrsfs when OCR/translation uses \\mathscr."""
    if _has_package(source, "mathrsfs"):
        return source
    if "\\mathscr" not in source:
        return source
    return _insert_before_document(source, "\\usepackage{mathrsfs}")


def _ensure_longequal_macro(source: str) -> str:
    """Define \\longequal when OCR/translation emits it without a package."""
    if "\\longequal" not in source:
        return source
    if "\\providecommand{\\longequal}" in source or "\\newcommand{\\longequal}" in source:
        return source
    return _insert_before_document(source, "\\providecommand{\\longequal}{=}")


def _ensure_coloneqq_macros(source: str) -> str:
    """Provide simple fallbacks for colon-equals macros often used in translated math."""
    if (
        "\\coloneqq" not in source
        and "\\eqqcolon" not in source
        and "\\Coloneqq" not in source
        and "\\Eqqcolon" not in source
    ):
        return source
    if "\\providecommand{\\coloneqq}" in source or "\\newcommand{\\coloneqq}" in source:
        return source
    source = _insert_before_document(source, "\\providecommand{\\coloneqq}{\\mathrel{:=}}")
    source = _insert_before_document(source, "\\providecommand{\\eqqcolon}{\\mathrel{=:}}")
    source = _insert_before_document(source, "\\providecommand{\\Coloneqq}{\\mathrel{::=}}")
    return _insert_before_document(source, "\\providecommand{\\Eqqcolon}{\\mathrel{=::}}")


def _ensure_pdflatex_unicode_support(source: str) -> str:
    """Inject minimal Unicode declarations needed for historical glyphs under pdfLaTeX."""
    if "ſ" not in source:
        return source
    source = _insert_before_document(source, "\\usepackage{textcomp}")
    source = _insert_before_document(source, "\\DeclareTextSymbol{\\textlongs}{TS1}{116}")
    source = _insert_before_document(source, "\\DeclareTextSymbolDefault{\\textlongs}{TS1}")
    return _insert_before_document(source, "\\DeclareUnicodeCharacter{017F}{\\textlongs}")


def _strip_xelatex_incompatible_unicode_declarations(source: str) -> str:
    """Remove pdfLaTeX-only Unicode declarations that XeLaTeX does not define."""
    return re.sub(
        r"(?m)^[ \t]*\\DeclareUnicodeCharacter\{017F\}\{\\textlongs\}\s*\n?",
        "",
        source,
    )


def _replace_documentclass_font_size(source: str, font_size_pt: int) -> str:
    """Replace or inject the top-level document font size option."""
    match = re.search(r"\\documentclass(?:\[(.*?)\])?\{([^}]+)\}", source)
    if not match:
        return source

    options = [opt.strip() for opt in (match.group(1) or "").split(",") if opt.strip()]
    options = [opt for opt in options if not re.fullmatch(r"\d+pt", opt)]
    options.insert(0, f"{font_size_pt}pt")
    replacement = f"\\documentclass[{','.join(options)}]{{{match.group(2)}}}"
    return source[: match.start()] + replacement + source[match.end() :]


def apply_source_layout_profile(source: str, layout_profile: dict | None) -> str:
    """Rewrite the documentclass size and geometry to better match the source scan."""
    if not layout_profile:
        return source

    updated = _replace_documentclass_font_size(
        source,
        int(layout_profile.get("font_size_pt", 10)),
    )
    geometry_options = layout_profile.get("geometry_options")
    if geometry_options:
        if re.search(r"\\geometry\{[^}]*\}", updated):
            updated = re.sub(
                r"\\geometry\{[^}]*\}",
                lambda _: f"\\geometry{{{geometry_options}}}",
                updated,
                count=1,
            )
        else:
            if "\\usepackage{geometry}" not in updated:
                updated = _insert_before_document(updated, "\\usepackage{geometry}")
            updated = _insert_before_document(updated, f"\\geometry{{{geometry_options}}}")

    comment = (
        "% Auto layout profile: "
        f"{layout_profile.get('page_width_in', '?')}in x "
        f"{layout_profile.get('page_height_in', '?')}in, "
        f"{layout_profile.get('font_size_pt', 10)}pt"
    )
    return _insert_before_document(updated, comment)


def prepare_latex_for_compile(source: str, compiler: str = "pdflatex") -> str:
    """Apply deterministic source fixes that preserve content but improve compilability."""
    prepared = normalize_latex_source(source)
    prepared = _normalize_symbolic_footnotes(prepared)
    prepared = _normalize_decimal_cdots_in_text(prepared)
    prepared = _ensure_graphicx_for_box_commands(prepared)
    prepared = _ensure_wrapfig_for_wrapped_floats(prepared)
    prepared = _ensure_tikz_for_tikzpicture(prepared)
    prepared = _ensure_amsmath_for_math_constructs(prepared)
    prepared = _ensure_amssymb_for_math_symbols(prepared)
    prepared = _ensure_mathrsfs_for_mathscr(prepared)
    prepared = _ensure_longequal_macro(prepared)
    prepared = _ensure_coloneqq_macros(prepared)
    if compiler == "pdflatex":
        prepared = _ensure_pdflatex_unicode_support(prepared)
    else:
        prepared = _strip_xelatex_incompatible_unicode_declarations(prepared)
    return prepared


def is_latex_document(source: str) -> bool:
    """Public validator used by pipeline guards."""
    src = source.strip()
    return "\\documentclass" in src or "\\begin{document}" in src


def _is_plausible_fix(old_source: str, new_source: str) -> bool:
    """Reject model 'fixes' that likely dropped substantial content."""
    old_len = len(old_source.strip())
    new_len = len(new_source.strip())
    if old_len == 0:
        return False
    # Compile fixes should not remove large portions of content.
    if new_len < int(old_len * 0.9):
        return False
    return True


def _latex_basename(path: str) -> str:
    normalized = path.replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1]


def _missing_graphic_width(options: str | None) -> str:
    if not options:
        return "0.8\\linewidth"
    match = re.search(r"width\s*=\s*([^,\]]+)", options)
    if match:
        return match.group(1).strip()
    return "0.8\\linewidth"


def _replace_missing_graphic_includes(source: str, error_log: str) -> str | None:
    """Replace missing image includes with deterministic fallbacks."""
    missing_files = {
        match.group(1).strip()
        for match in re.finditer(
            r"File [`']([^`']+\.(?:pdf|png|jpg|jpeg|eps))[`'] not found",
            error_log,
            re.IGNORECASE,
        )
    }
    if not missing_files:
        return None

    include_re = re.compile(
        r"^(?P<indent>\s*)\\includegraphics(?P<opts>\[[^\]]*\])?\{(?P<path>[^}]+)\}(?P<trail>\s*(?:%.*)?)$"
    )
    commented_tikz_begin = re.compile(r"^\s*%\s*\\begin\{tikzpicture\}")
    commented_tikz_end = re.compile(r"^\s*%\s*\\end\{tikzpicture\}")

    lines = source.splitlines(keepends=True)
    rewritten: list[str] = []
    changed = False
    index = 0

    while index < len(lines):
        line = lines[index]
        match = include_re.match(line)
        if not match:
            rewritten.append(line)
            index += 1
            continue

        path = match.group("path").strip()
        path_name = _latex_basename(path)
        if path not in missing_files and path_name not in missing_files:
            rewritten.append(line)
            index += 1
            continue

        indent = match.group("indent")
        fallback_start = None
        fallback_end = None
        probe = index + 1
        while probe < len(lines):
            stripped = lines[probe].strip()
            if not stripped:
                probe += 1
                continue
            if not lines[probe].lstrip().startswith("%"):
                break
            if commented_tikz_begin.match(lines[probe]):
                fallback_start = probe
                probe += 1
                while probe < len(lines):
                    if commented_tikz_end.match(lines[probe]):
                        fallback_end = probe
                        break
                    probe += 1
                break
            probe += 1

        changed = True
        if fallback_start is not None and fallback_end is not None:
            rewritten.append(f"{indent}% Restored TikZ fallback for missing graphic: {path_name}\n")
            for fallback_line in lines[fallback_start : fallback_end + 1]:
                rewritten.append(re.sub(r"^(\s*)%\s?", r"\1", fallback_line))
            index = fallback_end + 1
            continue

        width = _missing_graphic_width(match.group("opts"))
        rewritten.append(f"{indent}% Missing source graphic: {path_name}\n")
        rewritten.append(
            f"{indent}\\fbox{{\\parbox[c][8em][c]{{{width}}}{{\\centering\\footnotesize Source diagram unavailable}}}}\n"
        )
        index += 1

    if not changed:
        return None
    return "".join(rewritten)


def _apply_common_compile_fix(source: str, error_log: str, compiler: str) -> str | None:
    """Apply deterministic fixes for common compiler/runtime issues."""
    normalized = prepare_latex_for_compile(source, compiler)
    working_source = normalized
    missing_graphics = _replace_missing_graphic_includes(working_source, error_log)
    if missing_graphics and missing_graphics != working_source:
        return prepare_latex_for_compile(missing_graphics, compiler)
    if working_source != source:
        return working_source
    if (
        compiler == "pdflatex"
        and "font expansion" in error_log.lower()
        and "\\microtypesetup{expansion=false}" not in working_source
    ):
        # Disable expansion when non-scalable fonts trigger pdfTeX microtype errors.
        if "microtype" in working_source:
            package_line = re.search(r"(\\usepackage\{[^}]*microtype[^}]*\})", working_source)
            if package_line:
                return working_source.replace(
                    package_line.group(1),
                    package_line.group(1) + "\n\\microtypesetup{expansion=false}",
                    1,
                )
            if "\\begin{document}" in working_source:
                return working_source.replace(
                    "\\begin{document}",
                    "\\microtypesetup{expansion=false}\n\\begin{document}",
                    1,
                )
    if "missing $ inserted" in error_log.lower() and "\\cdot" in working_source:
        # Common OCR/LLM artifact: \cdot emitted in text mode (often in fancyfoot).
        fixed = re.sub(
            r"\\cdot(?!\s*\$)",
            r"$\\cdot$",
            working_source,
        )
        if fixed != working_source:
            return fixed
    if compiler == "xelatex" and "fontspec" in error_log.lower() and "cannot be found" in error_log.lower():
        # Replace unavailable font with a common Windows Korean font fallback.
        if "\\setmainfont{" in working_source:
            return re.sub(
                r"\\setmainfont\{[^}]+\}",
                r"\\setmainfont{Malgun Gothic}",
                working_source,
                count=1,
            )
        # If no explicit main font exists, add one after kotex.
        if "\\usepackage{kotex}" in working_source and "\\setmainfont{" not in working_source:
            return working_source.replace("\\usepackage{kotex}", "\\usepackage{kotex}\n\\setmainfont{Malgun Gothic}")
    return None


def compile_latex(
    source: str,
    output_dir: str,
    filename: str,
    compiler: str = "pdflatex",
) -> tuple[bool, str, str]:
    """
    Compile LaTeX source to PDF.
    Returns (success, pdf_path, error_log).
    """
    _ensure_latex_on_path()
    os.makedirs(output_dir, exist_ok=True)
    tex_path = os.path.join(output_dir, f"{filename}.tex")
    source = prepare_latex_for_compile(source, compiler)
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(source)
    compile_timeout_sec = _latex_compile_timeout_sec()

    cmd = [
        compiler,
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={output_dir}",
        tex_path,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=compile_timeout_sec, encoding="utf-8",
            errors="replace",
        )
        log_path = os.path.join(output_dir, f"{filename}.log")
        error_log = ""
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                error_log = lf.read()

        pdf_path = os.path.join(output_dir, f"{filename}.pdf")
        success = result.returncode == 0 and os.path.exists(pdf_path)
        return success, pdf_path, error_log
    except subprocess.TimeoutExpired:
        return False, "", f"Compilation timed out after {compile_timeout_sec} seconds."
    except FileNotFoundError:
        return False, "", f"Compiler '{compiler}' not found. Is it installed?"


def auto_fix_loop(
    source: str,
    output_dir: str,
    filename: str,
    max_attempts: int = 5,
    compiler: str = "pdflatex",
    fix_system_prompt: str = STEP3_SYS,
    fix_user_template: str = STEP3_USR,
    double_compile: bool = False,
) -> tuple[bool, str, str]:
    """
    STEP 3/7: Compile LaTeX, and if it fails, ask Gemini to fix errors.
    Returns (success, final_source, pdf_path).
    """
    current_source = prepare_latex_for_compile(source, compiler)

    for attempt in range(1, max_attempts + 1):
        print(f"  [COMPILE] Attempt {attempt}/{max_attempts} ({compiler})...")
        success, pdf_path, error_log = compile_latex(
            current_source, output_dir, filename, compiler
        )

        if success:
            print(f"  [COMPILE] Success on attempt {attempt}.")
            if double_compile:
                # Double-compile for cross-references (optional)
                compile_latex(current_source, output_dir, filename, compiler)
            # Clear any previous error log on success.
            err_log_path = os.path.join(output_dir, f"{filename}_error.log")
            if os.path.exists(err_log_path):
                try:
                    os.remove(err_log_path)
                except OSError:
                    pass
            pdf_path = os.path.join(output_dir, f"{filename}.pdf")
            return True, current_source, pdf_path

        deterministic = _apply_common_compile_fix(current_source, error_log, compiler)
        if deterministic:
            print("  [COMPILE] Applied deterministic fix and retrying...")
            current_source = prepare_latex_for_compile(deterministic, compiler)
            continue

        print(f"  [COMPILE] Failed attempt {attempt}. Requesting fix...")

        # Extract last 200 lines of error log for context
        log_lines = error_log.split("\n")
        truncated_log = "\n".join(log_lines[-200:]) if len(log_lines) > 200 else error_log

        user_prompt = fix_user_template.format(
            attempt_number=attempt,
            latex_source=current_source,
            error_log=truncated_log,
        )

        fix_response = call_text(fix_system_prompt, user_prompt)
        corrected = extract_block(fix_response, "CORRECTED_LATEX")
        if corrected:
            normalized = prepare_latex_for_compile(corrected, compiler)
            if is_latex_document(normalized):
                if _is_plausible_fix(current_source, normalized):
                    current_source = normalized
                else:
                    print("  [COMPILE] Warning: Ignored over-aggressive fix that removed content.")
            else:
                print("  [COMPILE] Warning: Ignored malformed corrected LaTeX from model.")
        else:
            print("  [COMPILE] Warning: Could not extract corrected LaTeX from response.")

    # Save error log on final failure
    err_log_path = os.path.join(output_dir, f"{filename}_error.log")
    with open(err_log_path, "w", encoding="utf-8") as f:
        f.write(error_log)
    print(f"  [COMPILE] All {max_attempts} attempts failed. Error log: {err_log_path}")
    return False, current_source, ""


def merge_pages(latex_pages: list[str]) -> str:
    """
    Merge multiple single-page LaTeX documents into one.
    Uses preamble from first page, body from all pages joined with \\newpage.
    """
    if len(latex_pages) == 1:
        return latex_pages[0]

    def split_doc(src: str) -> tuple[str, str]:
        """Split into (preamble, body) at \\begin{document}."""
        m = re.search(r"\\begin\{document\}", src)
        if not m:
            return src, ""
        preamble = src[: m.end()]
        rest = src[m.end() :]
        # Remove \end{document}
        rest = re.sub(r"\\end\{document\}\s*$", "", rest).strip()
        return preamble, rest

    preamble, first_body = split_doc(latex_pages[0])
    bodies = [first_body]

    for page_src in latex_pages[1:]:
        _, body = split_doc(page_src)
        bodies.append(body)

    merged_body = "\n\n\\newpage\n\n".join(bodies)
    return f"{preamble}\n{merged_body}\n\\end{{document}}"


def finalize_report(
    name: str,
    num_pages: int,
    digitalized_ok: bool,
    korean_ok: bool,
    output_dir: str,
    successful_pages: int | None = None,
    failed_pages: list[int] | None = None,
) -> str:
    """Generate quality report JSON."""
    failed_pages = failed_pages or []
    report = {
        "paper_name": name,
        "date": datetime.now().isoformat(),
        "total_pages": num_pages,
        "transcription": {
            "successful_pages": successful_pages if successful_pages is not None else num_pages,
            "failed_pages": failed_pages,
            "partial_output": bool(failed_pages),
        },
        "digitalized_pdf": {
            "compiled": digitalized_ok,
            "file": f"{name}_digitalized.pdf" if digitalized_ok else None,
        },
        "korean_pdf": {
            "compiled": korean_ok,
            "file": f"{name}_Korean.pdf" if korean_ok else None,
        },
    }
    report_path = os.path.join(output_dir, f"{name}_quality_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  [REPORT] Quality report saved: {report_path}")
    return report_path

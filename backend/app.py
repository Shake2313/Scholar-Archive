"""
논문 디지털화 & 한국어 번역 파이프라인 — Streamlit UI
Run:  streamlit run backend/app.py
"""

import base64
import os
import sys
import tempfile
import threading
import time
import queue
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from backend.app_output import (
    find_pipeline_state,
    load_manual_metadata_override,
    read_json,
    read_metadata_report,
    read_rights_metadata,
)
from backend.operations import build_operations_summary, summarize_output_directory
from backend.publish import (
    delete_metadata_override,
    metadata_override_path,
    save_metadata_override,
)
from backend.steps import compile_latex

# ── 페이지 설정 ─────────────────────────────────────────────────
st.set_page_config(page_title="논문 파이프라인", page_icon="📜", layout="wide")

# ── 세션 상태 초기화 ────────────────────────────────────────────
for key, default in {
    "pipeline_running": False,
    "pipeline_done": False,
    "pipeline_log": [],
    "pipeline_error": None,
    "output_dir": None,
    "pipeline_event_queue": None,
    "author_input": "",
    "publication_year_input": "",
    "death_year_input": "",
    "rights_meta_source": None,
    "metadata_override_notice": None,
    "metadata_editor_source": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


METADATA_OVERRIDE_FIELD_SPECS = (
    ("title", "Title"),
    ("author", "Author"),
    ("publication_year", "Publication year"),
    ("death_year", "Author death year"),
    ("journal_or_book", "Journal or book"),
    ("volume", "Volume"),
    ("issue", "Issue"),
    ("pages", "Pages"),
    ("language", "Language"),
    ("doi", "DOI"),
)


def _drain_pipeline_events():
    q = st.session_state.get("pipeline_event_queue")
    if q is None:
        return
    while True:
        try:
            event_type, payload = q.get_nowait()
        except queue.Empty:
            break
        if event_type == "log":
            st.session_state["pipeline_log"].append(payload)
        elif event_type == "error":
            st.session_state["pipeline_error"] = payload
        elif event_type == "done":
            st.session_state["pipeline_running"] = False
            st.session_state["pipeline_done"] = True
            st.session_state["pipeline_event_queue"] = None

# ── 유틸 함수 ───────────────────────────────────────────────────
def refresh_metadata_editor_state(output_path: Path, overrides: dict):
    source_key = str(output_path.resolve())
    if st.session_state.get("metadata_editor_source") == source_key:
        return
    for field, _label in METADATA_OVERRIDE_FIELD_SPECS:
        st.session_state[f"metadata_override_{field}"] = str(overrides.get(field) or "")
    st.session_state["metadata_editor_source"] = source_key


def apply_rights_metadata(source_key: str, metadata: dict | None = None):
    if st.session_state.get("rights_meta_source") == source_key:
        return
    metadata = metadata or {}
    st.session_state["author_input"] = str(metadata.get("author") or "")
    st.session_state["publication_year_input"] = str(metadata.get("publication_year") or "")
    st.session_state["death_year_input"] = str(metadata.get("death_year") or "")
    st.session_state["rights_meta_source"] = source_key


def pdf_iframe(path: Path):
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode()
    html = (
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="700" type="application/pdf"></iframe>'
    )
    st.markdown(html, unsafe_allow_html=True)


def download_btn(path: Path, label: str):
    st.download_button(label, data=path.read_bytes(), file_name=path.name)


_drain_pipeline_events()


def _start_pipeline_run(
    paper_name: str,
    output_dir: str,
    event_queue,
    pdf_bytes: bytes | None = None,
    input_pdf_path: str | None = None,
    pages: str | None = None,
    author: str | None = None,
    publication_year: int | None = None,
    death_year: int | None = None,
    retry_pages: str | None = None,
    workers: int = 4,
    translation_chunk_pages: int = 4,
):
    thread = threading.Thread(
        target=_run_pipeline_thread,
        kwargs={
            "paper_name": paper_name,
            "output_dir": output_dir,
            "event_queue": event_queue,
            "pdf_bytes": pdf_bytes,
            "input_pdf_path": input_pdf_path,
            "pages": pages,
            "author": author,
            "publication_year": publication_year,
            "death_year": death_year,
            "retry_pages": retry_pages,
            "workers": workers,
            "translation_chunk_pages": translation_chunk_pages,
        },
        daemon=True,
    )
    thread.start()


def _run_pipeline_thread(
    paper_name: str,
    output_dir: str,
    event_queue,
    pdf_bytes: bytes | None = None,
    input_pdf_path: str | None = None,
    pages: str | None = None,
    author: str | None = None,
    publication_year: int | None = None,
    death_year: int | None = None,
    retry_pages: str | None = None,
    workers: int = 4,
    translation_chunk_pages: int = 4,
):
    """파이프라인을 별도 스레드에서 실행하며 로그를 session_state에 기록."""
    import io

    # PDF를 임시 파일로 저장
    tmp_path = None
    input_path = input_pdf_path
    if pdf_bytes is not None:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.write(pdf_bytes)
        tmp.close()
        tmp_path = tmp.name
        input_path = tmp_path

    if not input_path:
        event_queue.put(("error", "No input PDF available for this run."))
        event_queue.put(("done", None))
        return

    log_buf = io.StringIO()
    event_queue.put(("log", "[THREAD] Pipeline thread started"))
    try:
        # pipeline 모듈이 같은 폴더에 있으므로 sys.path에 추가
        project_dir = str(PROJECT_ROOT)
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        from backend.pipeline import redirect_pipeline_output, run_pipeline

        # stdout/stderr를 캡처하면서 session_state 로그에도 실시간 추가
        class LogCapture:
            def __init__(self, buf):
                self.buf = buf
            def write(self, s):
                if s.strip():
                    self.buf.write(s)
                    event_queue.put(("log", s.rstrip()))
            def flush(self):
                pass
            def reconfigure(self, **kwargs):
                # Called by pipeline.py on Windows; no-op for this capture stream.
                return self

        capture = LogCapture(log_buf)
        with redirect_pipeline_output(
            output_dir,
            paper_name,
            stdout_stream=capture,
            stderr_stream=capture,
        ):
            run_pipeline(
                input_path,
                paper_name,
                output_dir,
                pages,
                author=author,
                publication_year=publication_year,
                death_year=death_year,
                workers=workers,
                translation_chunk_pages=translation_chunk_pages,
                retry_pages=retry_pages,
            )

        event_queue.put(("error", None))
    except Exception as e:
        event_queue.put(("error", str(e)))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        event_queue.put(("done", None))


# ── 사이드바: 파일 업로드 & 파이프라인 실행 ──────────────────────
with st.sidebar:
    st.header("논문 업로드")
    uploaded = st.file_uploader(
        "PDF 파일을 드래그하거나 클릭하여 업로드",
        type=["pdf"],
        accept_multiple_files=False,
    )

    if uploaded is not None:
        apply_rights_metadata(
            f"upload:{uploaded.name}:{getattr(uploaded, 'size', '')}",
            {},
        )

    paper_name = st.text_input(
        "논문 이름 (출력 파일명에 사용)",
        value=uploaded.name.rsplit(".", 1)[0] if uploaded else "",
        help="예: Einstein_1905",
    )

    # 출력 폴더 — 기본값은 프로젝트 내 output/<논문이름>
    default_out = str(PROJECT_ROOT / "output" / paper_name) if paper_name else ""
    output_dir_input = st.text_input("출력 폴더", value=default_out)

    pages_input = st.text_input(
        "처리할 페이지 (선택사항)",
        placeholder="예: 1-3  또는  1,3,5",
        help="비워두면 전체 페이지를 처리합니다.",
    )

    st.caption("Rights Check Metadata (optional)")
    author_input = st.text_input("Author", key="author_input", placeholder="e.g. Emmy Noether")
    publication_year_input = st.text_input(
        "Publication year",
        key="publication_year_input",
        placeholder="e.g. 1918",
    )
    death_year_input = st.text_input(
        "Author death year",
        key="death_year_input",
        placeholder="e.g. 1935",
    )
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        run_btn = st.button(
            "파이프라인 실행",
            type="primary",
            disabled=not uploaded or not paper_name or st.session_state["pipeline_running"],
            width="stretch",
        )
    with col2:
        if st.button("초기화", width="stretch"):
            st.session_state["pipeline_running"] = False
            st.session_state["pipeline_done"] = False
            st.session_state["pipeline_log"] = []
            st.session_state["pipeline_error"] = None
            st.session_state["output_dir"] = None
            st.session_state["pipeline_event_queue"] = None
            st.session_state["author_input"] = ""
            st.session_state["publication_year_input"] = ""
            st.session_state["death_year_input"] = ""
            st.session_state["rights_meta_source"] = None
            st.rerun()

    # 파이프라인 실행 트리거
    if run_btn and uploaded and paper_name:
        st.session_state["pipeline_running"] = True
        st.session_state["pipeline_done"] = False
        st.session_state["pipeline_log"] = []
        st.session_state["pipeline_error"] = None
        st.session_state["output_dir"] = output_dir_input

        pdf_bytes = uploaded.getvalue()
        pages = pages_input.strip() or None
        author = author_input.strip() or None
        try:
            publication_year = int(publication_year_input.strip()) if publication_year_input.strip() else None
        except ValueError:
            publication_year = None
        try:
            death_year = int(death_year_input.strip()) if death_year_input.strip() else None
        except ValueError:
            death_year = None
        event_queue = queue.Queue()
        st.session_state["pipeline_event_queue"] = event_queue

        _start_pipeline_run(
            paper_name=paper_name,
            output_dir=output_dir_input,
            event_queue=event_queue,
            pdf_bytes=pdf_bytes,
            pages=pages,
            author=author,
            publication_year=publication_year,
            death_year=death_year,
        )
        st.rerun()

    # 진행 상태 표시
    if st.session_state["pipeline_running"]:
        st.info("파이프라인 실행 중...")
        st.spinner("처리 중")

    if st.session_state["pipeline_error"]:
        st.error(f"오류 발생: {st.session_state['pipeline_error']}")

    if st.session_state["pipeline_done"] and not st.session_state["pipeline_error"]:
        st.success("파이프라인 완료!")

    # 기존 결과 폴더 불러오기
    st.divider()
    st.subheader("기존 결과 보기")
    existing_dir = st.text_input(
        "결과 폴더 경로",
        value=str(PROJECT_ROOT / "test_output"),
        key="existing_dir",
    )
    if st.button("불러오기", width="stretch"):
        if Path(existing_dir).is_dir():
            st.session_state["output_dir"] = existing_dir
            st.session_state["pipeline_done"] = True
            st.session_state["pipeline_error"] = None
            apply_rights_metadata(
                f"output:{Path(existing_dir).resolve()}",
                read_rights_metadata(Path(existing_dir)),
            )
            st.rerun()
        else:
            st.error("폴더를 찾을 수 없습니다.")


# ── 메인 영역 ───────────────────────────────────────────────────
st.title("📜 논문 디지털화 & 한국어 번역")

operations_root = PROJECT_ROOT / "output"
operations_summary = build_operations_summary(operations_root)

with st.expander("운영 요약", expanded=True):
    st.caption(f"스캔 루트: {operations_summary['output_root']}")
    documents = operations_summary["documents"]
    if documents:
        counts = operations_summary["counts"]
        c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns(9)
        c1.metric("결과 폴더", counts["total_outputs"])
        c2.metric("게시 완료", counts["published_outputs"])
        c3.metric("게시 대기", counts["ready_to_publish_outputs"])
        c4.metric("게시 실패", counts["publish_failed_outputs"])
        c5.metric("부분 완성", counts["partial_outputs"])
        c6.metric("리포트 없음", counts["missing_quality_reports"])
        c7.metric("메타 검토", counts["metadata_review_outputs"])
        c8.metric("권리 검토", counts["rights_review_outputs"])
        c9.metric("컴파일 경고", counts["compile_warning_outputs"])

        summary_rows = [
            {
                "폴더": item["folder_name"],
                "제목": item["title"],
                "페이지": item["total_pages"] or "-",
                "실패 페이지": ", ".join(str(page) for page in item["failed_pages"]) or "-",
                "게시": item["publish_status"],
                "메타데이터 검토": item["metadata_review_summary"] or "-",
                "권리 검토": item["rights_review_summary"] or "-",
                "컴파일 경고": item["compile_warning_summary"] or "-",
                "게시 이슈": item["publish_issue_summary"] or "-",
                "다음 작업": item["next_action"],
                "최근 갱신": item["updated_at"] or "-",
            }
            for item in documents
        ]
        st.dataframe(summary_rows, hide_index=True, use_container_width=True)

        doc_labels = {
            item["path"]: (
                f"{item['folder_name']} [{item['publish_status']}] - "
                f"{item['publish_issue_summary'] or item['next_action']}"
            )
            for item in documents
        }
        selected_output_dir = st.selectbox(
            "요약에서 결과 폴더 열기",
            options=list(doc_labels),
            format_func=lambda value: doc_labels[value],
            key="summary_output_dir",
        )
        if st.button("선택한 결과 폴더 열기", width="stretch"):
            st.session_state["output_dir"] = selected_output_dir
            st.session_state["pipeline_done"] = True
            st.session_state["pipeline_error"] = None
            apply_rights_metadata(
                f"output:{Path(selected_output_dir).resolve()}",
                read_rights_metadata(Path(selected_output_dir)),
            )
            st.rerun()
    else:
        st.info("output/ 아래에 집계할 결과 폴더가 없습니다.")

# ── 실행 로그 (실행 중이거나 완료 후) ────────────────────────────
if st.session_state["pipeline_running"] or st.session_state["pipeline_log"]:
    with st.expander("실행 로그", expanded=st.session_state["pipeline_running"]):
        log_text = "\n".join(st.session_state["pipeline_log"][-100:])
        st.code(log_text, language="text")
        if st.session_state["pipeline_running"]:
            time.sleep(2)
            st.rerun()

# ── 결과가 없으면 안내 메시지 ────────────────────────────────────
output_dir = st.session_state.get("output_dir")
if not output_dir or not Path(output_dir).is_dir():
    st.info("왼쪽 사이드바에서 PDF를 업로드하고 파이프라인을 실행하거나, 기존 결과 폴더를 불러오세요.")
    st.stop()

output_path = Path(output_dir)
current_output_summary = None
try:
    current_output_summary = summarize_output_directory(output_path)
except FileNotFoundError as exc:
    current_output_summary = None
    st.warning(f"결과 폴더 정보를 불러올 수 없습니다: {exc}")
except Exception as exc:
    current_output_summary = None
    st.warning(f"결과 폴더 분석 중 오류가 발생했습니다: {exc}")
current_output_name, current_metadata_override = load_manual_metadata_override(output_path)
current_metadata_report = read_metadata_report(output_path) or {}
refresh_metadata_editor_state(output_path, current_metadata_override)
if uploaded is None:
    apply_rights_metadata(
        f"output:{output_path.resolve()}",
        read_rights_metadata(output_path),
    )
pipeline_state = find_pipeline_state(output_path)
failed_pages = []
if pipeline_state:
    failed_pages = [
        int(page)
        for page in pipeline_state.get("failed_pages", [])
        if isinstance(page, int) or isinstance(page, float) or str(page).isdigit()
    ]

# ── 품질 보고서 요약 ────────────────────────────────────────────
report_files = sorted(output_path.glob("*_quality_report.json"))
report = None
publish_report_files = sorted(output_path.glob("*_publish_report.json"))
publish_report = read_json(publish_report_files[0]) if publish_report_files else None
if report_files:
    report = read_json(report_files[0])
    pname = report.get("paper_name", output_path.name)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("논문", pname)
    c2.metric("페이지", report.get("total_pages", "?"))
    dig_status = "OK" if report.get("digitalized_pdf", {}).get("compiled") else "FAIL"
    kor_status = "OK" if report.get("korean_pdf", {}).get("compiled") else "FAIL"
    dig_err = list(output_path.glob("*_digitalized_error.log"))
    kor_err = list(output_path.glob("*_Korean_error.log"))
    if dig_err:
        dig_status = "FAIL"
    if kor_err:
        kor_status = "FAIL"
    c3.metric("디지털화 PDF", dig_status)
    c4.metric("한국어 PDF", kor_status)
    report_failed_pages = report.get("transcription", {}).get("failed_pages", [])
    if not failed_pages:
        failed_pages = report_failed_pages
    c5.metric("실패 페이지", len(failed_pages))
    # Fallback: if pipeline log missed the "done" event, mark complete when report exists.
    if st.session_state.get("pipeline_running") and not st.session_state.get("pipeline_error"):
        st.session_state["pipeline_running"] = False
        st.session_state["pipeline_done"] = True
        st.session_state["pipeline_event_queue"] = None

if failed_pages:
    failed_pages = sorted({int(page) for page in failed_pages})
    st.warning(
        "필사에 실패한 페이지가 있어 현재 결과는 부분 완성본입니다. "
        f"실패 페이지: {failed_pages}"
    )
    retry_col, retry_info_col = st.columns([1, 2])
    with retry_col:
        retry_clicked = st.button(
            "실패한 페이지 재시도",
            type="primary",
            disabled=st.session_state["pipeline_running"],
            width="stretch",
        )
    with retry_info_col:
        st.caption("이미 성공한 페이지는 재사용하고, 실패한 페이지와 이후 결과물만 다시 갱신합니다.")

    if retry_clicked:
        if not pipeline_state:
            st.error("재시도에 필요한 상태 파일을 찾을 수 없습니다.")
        else:
            source_pdf = pipeline_state.get("source_pdf")
            if not source_pdf or not Path(source_pdf).is_file():
                st.error("원본 PDF를 찾을 수 없습니다. 다시 업로드해서 실행하세요.")
            else:
                st.session_state["pipeline_running"] = True
                st.session_state["pipeline_done"] = False
                st.session_state["pipeline_log"] = []
                st.session_state["pipeline_error"] = None
                st.session_state["output_dir"] = str(output_path)
                event_queue = queue.Queue()
                st.session_state["pipeline_event_queue"] = event_queue
                _start_pipeline_run(
                    paper_name=pipeline_state.get("paper_name", output_path.name),
                    output_dir=str(output_path),
                    event_queue=event_queue,
                    input_pdf_path=source_pdf,
                    pages=pipeline_state.get("pages_arg"),
                    author=pipeline_state.get("author"),
                    publication_year=pipeline_state.get("publication_year"),
                    death_year=pipeline_state.get("death_year"),
                    retry_pages=",".join(str(page) for page in failed_pages),
                    workers=int(pipeline_state.get("workers", 4) or 4),
                    translation_chunk_pages=int(
                        pipeline_state.get("translation_chunk_pages", 4) or 4
                    ),
                )
                st.rerun()

st.divider()

# ── 탭 구성 ─────────────────────────────────────────────────────
tabs = st.tabs([
    "원본 이미지",
    "디지털화 PDF",
    "한국어 PDF",
    "품질 보고서",
    "LaTeX 소스",
    "노트",
])

# ── 1. 원본 이미지 ──────────────────────────────────────────────
with tabs[0]:
    img_dir = output_path / "images"
    images = []
    if img_dir.is_dir():
        images = sorted(img_dir.glob("*.png")) + sorted(img_dir.glob("*.jpg"))
    if images:
        cols_per_row = st.slider("열 수", 1, 4, 3, key="img_cols")
        cols = st.columns(cols_per_row)
        for i, img in enumerate(images):
            with cols[i % cols_per_row]:
                st.image(str(img), caption=img.name, width="stretch")
    else:
        st.info("images/ 폴더에 이미지가 없습니다.")

# ── 2. 디지털화 PDF ─────────────────────────────────────────────
with tabs[1]:
    digitalized = sorted(output_path.glob("*_digitalized.pdf"))
    if digitalized:
        pdf_iframe(digitalized[0])
        download_btn(digitalized[0], "디지털화 PDF 다운로드")
    else:
        st.info("디지털화 PDF 파일이 없습니다.")

# ── 3. 한국어 PDF ───────────────────────────────────────────────
with tabs[2]:
    korean = sorted(output_path.glob("*_Korean.pdf"))
    if korean:
        pdf_iframe(korean[0])
        download_btn(korean[0], "한국어 PDF 다운로드")
    else:
        st.info("한국어 PDF 파일이 없습니다.")

# ── 4. 품질 보고서 ──────────────────────────────────────────────
with tabs[3]:
    if st.session_state.get("metadata_override_notice"):
        st.success(st.session_state["metadata_override_notice"])
        st.session_state["metadata_override_notice"] = None

    if report:
        st.json(report)
        download_btn(report_files[0], "품질 보고서 다운로드")
    else:
        st.info("품질 보고서 파일이 없습니다.")

    if current_output_summary and current_output_summary.get("metadata_review_rows"):
        st.subheader("메타데이터 검토")
        review_rows = [
            {
                "필드": row["label"],
                "최종 값": row["effective_value"] or "-",
                "최종 소스": row["effective_source"] or "-",
                "AI 값": row["ai_value"] or "-",
                "AI 신뢰도": row["ai_confidence"],
                "근거": row["ai_evidence"] or "-",
                "수동 보정": row["manual_override_value"] or "-",
                "검토 필요": "Yes" if row["review_needed"] else "-",
            }
            for row in current_output_summary["metadata_review_rows"]
        ]
        st.dataframe(review_rows, hide_index=True, use_container_width=True)

    if current_output_summary:
        st.subheader("권리 검토")
        rights_summary = current_output_summary.get("rights_review_summary")
        if rights_summary:
            if current_output_summary.get("rights_needs_manual_review"):
                st.warning(rights_summary)
            elif current_output_summary.get("rights_assessment") != "unknown":
                st.info(rights_summary)
            else:
                st.caption(rights_summary)
        rights_rows = [
            {
                "항목": "판단",
                "값": current_output_summary.get("rights_assessment") or "unknown",
            },
            {
                "항목": "사유",
                "값": current_output_summary.get("rights_reason") or "-",
            },
            {
                "항목": "소스",
                "값": current_output_summary.get("rights_source_summary") or "-",
            },
            {
                "항목": "수동 검토 필요",
                "값": "Yes" if current_output_summary.get("rights_needs_manual_review") else "-",
            },
        ]
        st.dataframe(rights_rows, hide_index=True, use_container_width=True)
        if current_output_summary.get("rights_warning_rows"):
            st.caption("권리 경고")
            st.dataframe(
                [{"경고": value} for value in current_output_summary["rights_warning_rows"]],
                hide_index=True,
                use_container_width=True,
            )

        st.subheader("컴파일 경고")
        if current_output_summary.get("compile_warning_rows"):
            compile_rows = [
                {
                    "대상": row["target"],
                    "심각도": row["severity"],
                    "메시지": row["message"],
                    "횟수": row["count"],
                }
                for row in current_output_summary["compile_warning_rows"]
            ]
            st.dataframe(compile_rows, hide_index=True, use_container_width=True)
        else:
            st.caption("감지된 문서 수준 컴파일 경고가 없습니다.")

    if current_output_name:
        st.subheader("수동 메타데이터 보정")
        st.caption(
            "여기서 저장한 값은 `[name]_metadata_override.json`에 기록되고, 운영 요약과 publish에서 즉시 우선 적용됩니다."
        )
        st.caption(f"Override file: {metadata_override_path(output_path, current_output_name)}")
        effective_metadata = (
            current_metadata_report.get("effective_metadata")
            if isinstance(current_metadata_report.get("effective_metadata"), dict)
            else {}
        )
        effective_sources = (
            current_metadata_report.get("effective_sources")
            if isinstance(current_metadata_report.get("effective_sources"), dict)
            else {}
        )
        with st.form("manual_metadata_override_form"):
            left_col, right_col = st.columns(2)
            for index, (field, label) in enumerate(METADATA_OVERRIDE_FIELD_SPECS):
                column = left_col if index % 2 == 0 else right_col
                current_value = effective_metadata.get(field)
                current_source = effective_sources.get(field) or "-"
                with column:
                    st.text_input(
                        label,
                        key=f"metadata_override_{field}",
                        placeholder=str(current_value) if current_value is not None else "",
                    )
                    st.caption(
                        f"Current: {current_value if current_value is not None else '-'} ({current_source})"
                    )
            save_override_clicked = st.form_submit_button(
                "수동 보정 저장",
                type="primary",
                width="stretch",
            )

        override_file_exists = Path(
            metadata_override_path(output_path, current_output_name)
        ).exists()
        clear_override_clicked = st.button(
            "보정 파일 제거",
            disabled=not override_file_exists,
            width="stretch",
        )

        if save_override_clicked:
            override_inputs = {
                field: st.session_state.get(f"metadata_override_{field}", "")
                for field, _label in METADATA_OVERRIDE_FIELD_SPECS
            }
            if any(str(value).strip() for value in override_inputs.values()):
                override_path_value = save_metadata_override(
                    output_path,
                    current_output_name,
                    override_inputs,
                )
                st.session_state["metadata_override_notice"] = (
                    f"수동 메타데이터 보정을 저장했습니다: {override_path_value}"
                )
            else:
                removed_path = delete_metadata_override(output_path, current_output_name)
                st.session_state["metadata_override_notice"] = (
                    f"수동 메타데이터 보정을 제거했습니다: {removed_path}"
                    if removed_path
                    else "저장된 수동 메타데이터 보정이 없었습니다."
                )
            st.session_state["metadata_editor_source"] = None
            st.session_state["rights_meta_source"] = None
            st.rerun()

        if clear_override_clicked:
            removed_path = delete_metadata_override(output_path, current_output_name)
            st.session_state["metadata_override_notice"] = (
                f"수동 메타데이터 보정을 제거했습니다: {removed_path}"
                if removed_path
                else "저장된 수동 메타데이터 보정이 없었습니다."
            )
            st.session_state["metadata_editor_source"] = None
            st.session_state["rights_meta_source"] = None
            st.rerun()
    else:
        st.info("수동 메타데이터 보정을 하려면 output 이름을 추론할 수 있어야 합니다.")

    if publish_report:
        st.subheader("게시 리포트")
        st.json(publish_report)
        download_btn(publish_report_files[0], "게시 리포트 다운로드")

# ── 5. LaTeX 소스 ───────────────────────────────────────────────
with tabs[4]:
    tex_files = sorted(output_path.glob("*.tex"))
    if tex_files:
        selected = st.selectbox("TeX 파일 선택", tex_files, format_func=lambda p: p.name)
        default_content = selected.read_text(encoding="utf-8")
        state_key = f"latex_edit_{selected.name}"
        if state_key not in st.session_state:
            st.session_state[state_key] = default_content

        left, right = st.columns(2)
        with left:
            st.subheader("LaTeX 편집")
            st.text_area(
                "편집 영역",
                key=state_key,
                height=500,
                label_visibility="collapsed",
            )
            auto_compiler = "xelatex" if (
                "\\usepackage{kotex}" in st.session_state[state_key]
                or "\\setmainfont" in st.session_state[state_key]
            ) else "pdflatex"
            compiler = st.selectbox(
                "컴파일러",
                ["xelatex", "pdflatex"],
                index=0 if auto_compiler == "xelatex" else 1,
            )
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("컴파일", key=f"compile_{selected.name}", type="primary", width="stretch"):
                    ok, pdf_path, error_log = compile_latex(
                        st.session_state[state_key],
                        str(output_path),
                        selected.stem,
                        compiler=compiler,
                    )
                    st.session_state[f"compile_ok_{selected.name}"] = ok
                    st.session_state[f"compile_err_{selected.name}"] = error_log
            with col_b:
                if st.button("초기화", key=f"reset_{selected.name}", width="stretch"):
                    st.session_state[state_key] = default_content
                    st.rerun()

            compile_ok = st.session_state.get(f"compile_ok_{selected.name}")
            compile_err = st.session_state.get(f"compile_err_{selected.name}")
            if compile_ok is True:
                st.success("컴파일 성공")
            elif compile_ok is False:
                st.error("컴파일 실패")
                if compile_err:
                    st.code(compile_err, language="text")

        with right:
            st.subheader("PDF 미리보기")
            pdf_path = output_path / f"{selected.stem}.pdf"
            if pdf_path.exists():
                pdf_iframe(pdf_path)
                download_btn(pdf_path, f"{pdf_path.name} 다운로드")
            else:
                st.info("PDF가 없습니다. 컴파일 후 확인하세요.")
    else:
        st.info("LaTeX 파일이 없습니다.")
with tabs[5]:
    note_files = sorted(output_path.glob("*_notes.txt"))
    if note_files:
        for nf in note_files:
            with st.expander(nf.name, expanded=True):
                st.text(nf.read_text(encoding="utf-8"))
                download_btn(nf, f"{nf.name} 다운로드")
    else:
        st.info("노트 파일이 없습니다.")

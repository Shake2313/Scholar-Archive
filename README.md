# Scholar Archive

옛 논문 PDF를 LaTeX 기반 디지털 원문과 한국어 번역본으로 변환하는 파이프라인입니다.

## 핵심 원칙

이 프로젝트의 최우선 목표는 옛 논문의 형식, 문법, 표기, 수식, 문체, 개념 표현을 가능한 한 그대로 고증하는 것입니다.

- 원문에 있는 오래된 문법, 철자, 용어, 개념 표현을 임의로 현대화하지 않습니다.
- 19세기 스타일의 문장, 지금 기준에서 부정확해 보이는 개념, 시대 특유의 표기법도 원문 일부로 간주합니다.
- AI가 내용을 보고 "틀렸다"거나 "낡았다"고 판단해 멋대로 수정하는 것은 금지합니다.
- 목표는 교정이나 현대화가 아니라 faithful transcription과 historical reproduction입니다.
- 애매한 부분이 있으면 조용히 고치지 말고 표시하거나 검토 대상으로 남기는 쪽이 맞습니다.

즉, 이 프로젝트는 옛 논문을 현대 독자에게 맞게 다듬는 도구가 아니라, 원문을 최대한 손대지 않고 디지털 형태로 복원하는 도구입니다.

## 개요

- 입력: 스캔된 논문 PDF
- 출력: 페이지 이미지, 디지털화된 LaTeX/PDF, 한국어 LaTeX/PDF, 번역 노트, 품질 리포트, 권리 체크 로그
- 실행 방식: CLI(`pipeline.py`) 또는 Streamlit UI(`app.py`)

## 주요 기능

- PDF를 페이지 이미지로 변환
- 페이지 구조 분석과 LaTeX 전사
- LaTeX 병합 및 `pdflatex`/`xelatex` 컴파일
- 컴파일 실패 시 자동 수정 루프 수행
- 한국어 번역 LaTeX/PDF 생성
- 품질 리포트와 권리 체크 JSON 생성

## 프로젝트 구조

- `pipeline.py`: 전체 파이프라인 오케스트레이션
- `steps.py`: PDF 처리, 모델 호출, LaTeX 컴파일, 자동 수정 공용 함수
- `prompts.py`: 전사/번역/자동 수정 프롬프트 상수
- `app.py`: Streamlit UI
- `tests/test_helpers.py`: 순수 helper 회귀 테스트

## 요구 사항

- Python 3.x
- `pip install -r requirements.txt`
- LaTeX 컴파일러
- `pdflatex`
- `xelatex`
- Gemini API 키 또는 Vertex/Google Cloud 기반 인증
- PDF 렌더링 백엔드
- PyMuPDF 또는 `pdf2image + Poppler`

## 환경 변수

- 모델 인증
- `GEMINI_API_KEY`
- 또는 `GOOGLE_API_KEY`
- 또는 `GOOGLE_GEMINI_API_KEY`
- 선택 사항
- `MODEL_NAME`
- `API_TIMEOUT_SEC`

## 실행

CLI:

```bash
python pipeline.py --input paper.pdf --name PaperName --output ./output/PaperName
```

페이지 범위 지정:

```bash
python pipeline.py --input paper.pdf --name PaperName --output ./output/PaperName --pages 1-3
```

Streamlit UI:

```bash
streamlit run app.py
```

또는 Windows에서:

```bat
run_streamlit.bat
```

## Windows launcher

작업표시줄에 고정해서 프로그램처럼 켜고 싶다면 `ScholarArchive.exe`를 사용할 수 있습니다.

- 이 exe는 완전 독립형 앱이 아니라 Streamlit 실행을 편하게 해주는 launcher입니다.
- 따라서 프로젝트 폴더와 Python 환경, 패키지 설치, LaTeX 도구는 그대로 필요합니다.
- `ScholarArchive.exe`는 프로젝트 루트에 두는 것이 가장 안전합니다.
- Windows에서 exe를 우클릭해서 작업표시줄에 고정하면 됩니다.

빌드 다시 하기:

```bat
build_launcher.bat
```

직접 명령으로 빌드:

```bash
python -m PyInstaller --noconfirm --onefile --noconsole --name ScholarArchive --distpath . --workpath build\pyinstaller --specpath build\pyinstaller launcher.py
```

특정 Python으로 실행하고 싶으면 환경 변수 `SCHOLAR_ARCHIVE_PYTHON`에 인터프리터 경로를 지정할 수 있습니다.

## preflight 체크

파이프라인 시작 시 아래 항목을 먼저 점검합니다.

- 모델 인증 상태
- PDF 처리 가능 여부
- `pdflatex`, `xelatex` 사용 가능 여부

치명적인 누락이 있으면 긴 작업을 시작하기 전에 바로 실패합니다.

## 테스트

문법 체크:

```bash
python -m py_compile pipeline.py app.py steps.py prompts.py tests/test_helpers.py
```

helper 테스트:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

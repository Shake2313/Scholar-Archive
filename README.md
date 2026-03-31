# Scholar Archive

Scholar Archive는 단순 번역 프로그램이 아니다. 스캔된 고문헌 PDF를 디지털 원문과 한국어 번역본으로 복원하고, 메타데이터와 함께 데이터베이스에 게시한 뒤, 웹에서 열람 가능한 공개 아카이브로 운영하기 위한 프로젝트다.

## 목표

- 옛 논문과 문헌을 LaTeX 기반 디지털 원문으로 최대한 충실하게 복원한다.
- 한국어 번역본, 메타데이터, 품질 리포트를 함께 보존한다.
- 결과물을 로컬 산출물로 끝내지 않고 Supabase에 게시한다.
- Vercel 웹에서 연대별, 저자별, 문서별로 탐색 가능한 디지털 도서관을 만든다.

즉 이 프로젝트의 목적은 "PDF를 번역해서 끝내는 도구"가 아니라 "축적되고 공개되는 연구용 디지털 도서관"이다.

## 핵심 원칙

- 원문의 철자, 문체, 표기, 구두점은 가능한 한 보존한다.
- AI가 내용을 현대적으로 정리하거나 요약하는 방향으로 개입하지 않는다.
- 결과물은 읽기 편의보다 historical reproduction과 faithful transcription을 우선한다.
- 번역과 메타데이터 추론은 원문 보존을 보조하는 수단이지, 원문을 대체하는 결과물이 아니다.

## 현재 구성

- `pipeline.py`
  - PDF 처리, 페이지 전사, 번역, 컴파일, 리포트 생성, 게시까지 담당하는 메인 파이프라인
- `steps.py`
  - PDF 렌더링, 모델 호출, LaTeX 보정, 컴파일 같은 공용 실행 로직
- `publish.py`
  - 게시 번들 생성, Supabase Storage/DB 업로드, 기존 산출물 재게시
- `app.py`
  - 로컬 운영용 Streamlit UI
- `frontend/`
  - Vercel 배포용 Next.js 웹 앱
- `supabase/schema.sql`
  - 공개 읽기 아카이브용 테이블, 버킷, RLS 정책
- `tests/test_helpers.py`
  - 핵심 helper 회귀 테스트

## 파이프라인 결과물

- 원본 PDF 복사본
- 페이지 이미지
- 디지털화된 LaTeX / PDF
- 한국어 LaTeX / PDF
- 전사 노트 / 번역 노트
- 품질 리포트
- 권리 체크 JSON
- AI 보강 메타데이터 JSON
- 게시 리포트 JSON

## 게시 및 웹 구조

- 저장소
  - Supabase Postgres: 문서, 저자, 페이지, 자산, 메타데이터 스냅샷
  - Supabase Storage: PDF, 이미지, TeX, JSON, 노트
- 공개 웹
  - 홈
  - 연대별 분류
  - 저자별 분류
  - 문서 상세 페이지
    - 원문 페이지 이미지
    - 디지털 원문 텍스트
    - 한국어 번역 텍스트
    - PDF 다운로드

## 실행 방식

CLI:

```bash
python pipeline.py --input paper.pdf --name PaperName --output ./output/PaperName
```

게시 없이 실행:

```bash
python pipeline.py --input paper.pdf --name PaperName --output ./output/PaperName --no-publish
```

기존 산출물 재게시:

```bash
python publish.py --output-dir ./output/PaperName --name PaperName
```

페이지 범위 지정:

```bash
python pipeline.py --input paper.pdf --name PaperName --output ./output/PaperName --pages 1-3
```

Streamlit UI:

```bash
streamlit run app.py
```

Frontend 개발 서버:

```bash
cd frontend
npm install
npm run dev
```

## 환경 변수

모델 호출:

- `GEMINI_API_KEY`
- 또는 `GOOGLE_API_KEY`
- 또는 `GOOGLE_GEMINI_API_KEY`

게시:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- 또는 `SUPABASE_SECRET_KEY`
- 선택 사항: `SUPABASE_STORAGE_BUCKET`

DB 스키마 적용:

- `DATABASE_POOLER_URL`
- 또는 `SUPABASE_DB_URL`
- 또는 `DATABASE_URL`

웹 공개 읽기:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

기타:

- `MODEL_NAME`
- `API_TIMEOUT_SEC`

## 배포 요약

1. `supabase/schema.sql`을 Supabase 프로젝트에 적용한다.
2. 파이프라인 환경에 `SUPABASE_URL`과 service key를 넣는다.
3. `frontend/`를 Vercel에 배포한다.
4. Vercel 환경 변수에 `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`를 넣는다.
5. 파이프라인이 문서를 처리하면 결과물이 자동 게시되고 웹에서 열람된다.

## Windows launcher

작업표시줄에서 로컬 운영 UI를 실행하려면 `ScholarArchive.exe`를 사용할 수 있다.

- 이 exe는 전체 앱을 패키징한 것이 아니라 Streamlit 실행용 launcher다.
- Python 환경, 패키지, LaTeX 도구는 별도로 설치되어 있어야 한다.

빌드:

```bat
build_launcher.bat
```

## 검증

문법 체크:

```bash
python -m py_compile pipeline.py publish.py app.py steps.py prompts.py tests/test_helpers.py
```

테스트:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

웹 빌드:

```bash
cd frontend
npm run build
```

## 운영 기록

Scholar Archive 작업에서 의미 있는 진전이 생기면 Notion에 개발 일지를 남긴다.

- 기준 문서: `Notion_Instruction.md`
- 기본 위치: Notion `Dev Log` 데이터베이스
- 상태 변경 추적: 필요 시 Notion `Tasks` 데이터베이스
- 기록 대상: 코드/설정/스키마/프롬프트/파이프라인 구조 변경, 버그 수정, blocker 해소, 의미 있는 결과물 생성, 이후 판단에 영향을 주는 실패
- 기록 제외: 사소한 재시도, 미세한 문구 수정, 결과 없는 탐색, 같은 작업의 중복 로그
- 기록 방식: 작은 로그 여러 개보다 의미 있는 작업 단위 하나로 묶어 작성하고, outcome 중심으로 간결하게 남긴다

Notion 기록이 필요한지 애매하면 "나중에 다시 봤을 때 남겨 둘 가치가 있는가?"를 기준으로 판단한다.

## 다음 참고

현재 작업 우선순위와 완료 이력은 [CODEX_CHECKLIST.md](C:/Users/박수인/Desktop/백업/Coding/Scholar%20Archive/CODEX_CHECKLIST.md)에 정리한다.
Notion 기록 원칙은 [Notion_Instruction.md](C:/Users/박수인/Desktop/백업/Coding/Scholar%20Archive/Notion_Instruction.md)를 따른다.

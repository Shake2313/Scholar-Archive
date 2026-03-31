# Codex Checklist

Last updated: 2026-03-20

## 목표

이 저장소의 목적은 로컬에서 PDF를 번역하고 끝내는 프로그램이 아니다. 스캔 문헌을 디지털 원문과 한국어 번역본으로 복원하고, 메타데이터와 함께 Supabase에 게시한 뒤, Vercel 웹에서 축적형 디지털 도서관으로 서비스하는 것이 목표다.

핵심 방향:

- 로컬 변환 도구
  - 문서 전사, 번역, 컴파일, 품질 검수
- 게시 파이프라인
  - 메타데이터, 자산, 페이지 데이터를 DB와 Storage에 업로드
- 공개 웹 아카이브
  - 홈, 분류 탐색, 문서 상세 열람, 다운로드

## 현재 상태

- `output/`은 산출물 보존 영역으로 유지한다.
- 기본 파이프라인은 Supabase publish까지 연결되어 있다.
- Supabase 스키마와 공개 읽기 정책은 적용됐다.
- 기존 산출물 일부는 이미 게시되어 웹 데이터 소스로 사용할 수 있다.

## 앞으로 할 일

### 배포 및 운영

- [ ] Vercel 프로젝트에 `frontend/`를 실제 배포하고 공개 URL을 확정한다.
- [ ] Vercel 환경 변수 `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`를 연결한다.
- [ ] 배포된 웹에서 홈, 연대별, 저자별, 상세 페이지를 실제 데이터로 검수한다.
- [ ] 웹에서 PDF 다운로드 링크와 페이지 이미지 로딩을 실사용 기준으로 확인한다.

### 문서 게시 운영

- [ ] 게시 가능한 `output/` 폴더를 전수 점검하고 남은 문서를 일괄 publish한다.
- [ ] publish 성공/실패를 한눈에 보는 운영용 요약 화면 또는 리포트 집계를 만든다.
- [ ] 문서 slug 충돌 정책과 재게시 정책을 명확히 문서화한다.
- [ ] 메타데이터가 부족한 문서에 대해 수동 보정 절차를 정리한다.

### 웹 제품 완성도

- [ ] 홈 화면에 최근 문서, 소개, 탐색 진입점을 실제 서비스 수준으로 다듬는다.
- [ ] 연대별 분류를 publication year / century 기준으로 더 읽기 좋게 정리한다.
- [ ] 저자별 페이지에 정렬, 필터, 문서 수 표시를 보강한다.
- [ ] 상세 페이지에서 원문 이미지와 디지털 원문/번역 탭 UX를 개선한다.
- [ ] 검색 기능을 강화해 제목, 저자, 저널, 연대 기준 검색이 되게 한다.

### 메타데이터와 품질

- [ ] AI 추론 메타데이터의 confidence와 evidence를 웹 또는 운영 화면에서 확인 가능하게 만든다.
- [ ] 메타데이터 수동 수정 기능 또는 관리자용 수정 경로를 만든다.
- [ ] rights 판단 로직과 표시 방식을 좀 더 보수적으로 다듬는다.
- [ ] 문서별 품질 리포트와 컴파일 경고를 운영 관점에서 요약한다.

### 코드 구조

- [ ] `run_pipeline()`을 더 작은 단계 함수로 분해해 유지보수성을 높인다.
- [ ] `app.py`의 결과 로딩과 표시 로직을 helper로 분리한다.
- [ ] publish 관련 로직과 report 로직을 더 분리해 테스트 가능성을 높인다.
- [ ] e2e 테스트 또는 게시 smoke test를 추가한다.

## 완료 이력 보존

### 파이프라인 안정화

- [x] 모델 키, PDF 처리, LaTeX 툴링을 검사하는 preflight 체크를 추가했다.
- [x] 일부 페이지 전사 실패 시 전체 중단 대신 partial output으로 계속 진행하게 만들었다.
- [x] 실패 페이지 재시도를 위한 pipeline state 저장과 UI 동작을 추가했다.
- [x] helper 함수 중심의 `unittest` 회귀 테스트를 추가했다.
- [x] LaTeX 컴파일 오류 자동 수정 루프를 유지하면서 보고 체계를 정리했다.

### 문서 복원 품질

- [x] glossary 기반 캐시/DB 경로를 제거하고 번역 흐름을 단순화했다.
- [x] 샘플 PDF 수동 검수로 큰 레이아웃 붕괴가 없는지 확인했다.
- [x] XeLaTeX 쪽 경고와 불필요한 엔진 불일치 코드를 정리했다.

### 메타데이터

- [x] 빈 PDF 메타데이터를 보완하기 위한 AI 기반 메타데이터 추론을 추가했다.
- [x] `*_metadata.json`에 raw/deterministic/ai/effective metadata를 저장하게 했다.
- [x] rights 판단에는 high-confidence 메타데이터만 반영하도록 보수적 기준을 넣었다.

### 게시와 데이터 저장

- [x] `publish.py`를 추가해 Supabase DB/Storage 게시 경로를 만들었다.
- [x] `supabase/schema.sql`에 문서/저자/페이지/자산/메타데이터 스냅샷 스키마를 정의했다.
- [x] 파이프라인 완료 후 자동 publish와 `*_publish_report.json` 저장을 연결했다.
- [x] 기존 `output/` 산출물을 재처리 없이 다시 올릴 수 있는 publish-only 경로를 만들었다.
- [x] Unicode 제목과 파일명에 대비한 ASCII-safe slug/storage path 처리를 넣었다.
- [x] Supabase MCP 경로를 연결하고 스키마 적용까지 완료했다.

### 웹 아카이브

- [x] `frontend/`에 Next.js App Router 웹 앱을 추가했다.
- [x] 홈, 연대별, 저자별, 문서 상세 페이지 기본 구조를 만들었다.
- [x] 상세 페이지에 원문 이미지와 디지털 원문/번역 병렬 열람 UI를 넣었다.
- [x] Vercel 배포를 전제로 한 환경 변수 구조를 정리했다.

### 운영 보조

- [x] Windows launcher(`ScholarArchive.exe`) 경로를 유지했다.
- [x] README를 "번역 도구"가 아니라 "게시형 디지털 도서관" 목적에 맞게 재정리했다.

## 참고 메모

- 현재 게시 데이터는 Supabase의 `documents`, `document_pages`, `document_assets` 등을 기준으로 읽는다.
- 웹 공개 읽기는 anon key 기반, 게시는 service role key 기반으로 분리한다.
- 다음 고가치 작업은 실제 Vercel 배포 검수와 남은 문서 일괄 publish 정리다.

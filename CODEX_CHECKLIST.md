# Codex Checklist

Last updated: 2026-03-31

## 목표

이 저장소의 목적은 로컬에서 PDF를 번역하고 끝내는 프로그램이 아니다. 스캔 문헌을 디지털 원문과 한국어 번역본으로 복원하고, 메타데이터와 함께 Supabase에 게시한 뒤, Vercel 웹에서 축적형 디지털 도서관으로 서비스하는 것이 목표다.

핵심 방향:

- 로컬 복원 파이프라인
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
- 운영 요약 화면과 legacy publish 경로는 추가됐지만, 장시간 재시도 비용을 줄이는 stage-isolated 복구 경로는 아직 부족하다.
- `달랑베르 파동방정식` 재시도를 통해, 웹 마감보다 운영 복구성과 실패 원인 가시성을 먼저 높이는 편이 더 고가치라는 점이 확인됐다.

## 앞으로 할 일

### 재시도 비용과 운영 안정성

- [ ] 번역-only, Korean PDF-only, metadata-only 재실행 경로를 명시적 CLI 옵션으로 분리한다.
- [ ] 캐시 재실행 시 이미지 재렌더링과 메타데이터 재추론을 기본적으로 건너뛰고, 필요한 단계만 강제로 다시 돌릴 수 있게 한다.
- [ ] `pipeline_state.json`과 운영 요약에 현재 단계, 마지막 성공 단계, 마지막 오류 원인, timeout/retry 설정을 남긴다.
- [ ] XeLaTeX와 번역 결과에서 자주 깨지는 매크로와 엔진별 호환성 보정을 deterministic rule 중심으로 더 확장한다.
- [ ] 장시간 실행 작업에 대해 표준 로그 파일, 마지막 진행 시각, hung-process 감지 기준을 정리한다.

### 문서 게시 운영

- [ ] publish 또는 일괄 재시도 전에 Supabase DNS/API 연결 상태를 먼저 점검하는 health check를 넣는다.
- [ ] 게시 가능한 `output/` 폴더를 전수 점검하고 남은 문서를 일괄 publish한다.
- [ ] 문서 slug 충돌 정책과 재게시 정책을 명확히 문서화한다.
- [ ] 메타데이터가 부족한 문서에 대해 수동 보정 절차를 정리한다.
- [ ] publish 장애 사유(DNS, 권한, 누락 파일)를 운영 요약에서 문서 단위로 바로 보이게 한다.

### 메타데이터와 품질

- [ ] AI 추론 메타데이터의 confidence와 evidence를 웹 또는 운영 화면에서 확인 가능하게 만든다.
- [ ] 메타데이터 수동 수정 기능 또는 관리자용 수정 경로를 만든다.
- [ ] rights 판단 로직과 표시 방식을 좀 더 보수적으로 다듬는다.
- [ ] 문서별 품질 리포트와 컴파일 경고를 운영 관점에서 요약한다.

### 배포 및 웹 검수

- [ ] Vercel 프로젝트에 `frontend/`를 실제 배포하고 공개 URL을 확정한다.
- [ ] Vercel 환경 변수 `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`를 연결한다.
- [ ] 배포된 웹에서 홈, 연대별, 저자별, 상세 페이지를 실제 데이터로 검수한다.
- [ ] 웹에서 PDF 다운로드 링크와 페이지 이미지 로딩을 실사용 기준으로 확인한다.

### 웹 제품 완성도

- [ ] 홈 화면에 최근 문서, 소개, 탐색 진입점을 실제 서비스 수준으로 다듬는다.
- [ ] 연대별 분류를 publication year / century 기준으로 더 읽기 좋게 정리한다.
- [ ] 저자별 페이지에 정렬, 필터, 문서 수 표시를 보강한다.
- [ ] 상세 페이지에서 원문 이미지와 디지털 원문/번역 탭 UX를 개선한다.
- [ ] 검색 기능을 강화해 제목, 저자, 저널, 연대 기준 검색이 되게 한다.

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
- [x] 메타데이터 프롬프트 렌더링을 분리해 예시 JSON 중괄호 때문에 재시도가 깨지지 않게 했다.
- [x] Gemini HTTP timeout/retry를 명시적으로 제어하게 만들었다.
- [x] LaTeX 컴파일 timeout을 환경변수로 조절할 수 있게 했다.
- [x] XeLaTeX에서 깨지는 pdflatex 전용 Unicode 선언과 `\longequal` 문제를 deterministic fix로 처리했다.

### 문서 복원 품질

- [x] glossary 기반 캐시/DB 경로를 제거하고 번역 흐름을 단순화했다.
- [x] 샘플 PDF 수동 검수로 큰 레이아웃 붕괴가 없는지 확인했다.
- [x] XeLaTeX 쪽 경고와 불필요한 엔진 불일치 코드를 정리했다.
- [x] `달랑베르 파동방정식` 문서의 장기 재시도를 마무리해 한국어 PDF와 품질 리포트를 복구했다.

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
- [x] `*_source.pdf`가 없는 legacy 산출물도 publish bundle로 재구성할 수 있게 했다.

### 웹 아카이브

- [x] `frontend/`에 Next.js App Router 웹 앱을 추가했다.
- [x] 홈, 연대별, 저자별, 문서 상세 페이지 기본 구조를 만들었다.
- [x] 상세 페이지에 원문 이미지와 디지털 원문/번역 병렬 열람 UI를 넣었다.
- [x] Vercel 배포를 전제로 한 환경 변수 구조를 정리했다.

### 운영 보조

- [x] Windows launcher(`ScholarArchive.exe`) 경로를 유지했다.
- [x] README를 "번역 도구"가 아니라 "게시형 디지털 도서관" 목적에 맞게 재정리했다.
- [x] `output/` 전체를 스캔하는 운영 요약 화면을 추가했다.

## 참고 메모

- 현재 게시 데이터는 Supabase의 `documents`, `document_pages`, `document_assets` 등을 기준으로 읽는다.
- 웹 공개 읽기는 anon key 기반, 게시는 service role key 기반으로 분리한다.
- 당분간 최우선은 웹 외형보다 재시도 비용 절감, 실패 원인 가시화, publish health check다.
- Supabase DNS가 안정화되기 전까지는 bulk publish를 기본 완료 기준으로 보지 않는다.

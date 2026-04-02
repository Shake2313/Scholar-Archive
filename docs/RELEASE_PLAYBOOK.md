# Release Playbook

This playbook defines the repeatable path from a local `output/` artifact to the live public archive.

## 1. Prepare Content

- Run the restoration pipeline or confirm that an existing `output/<name>/` folder is publish-ready.
- Review `*_metadata.json`, `*_metadata_override.json`, and `*_publish_report.json` if the document has weak metadata confidence or rights uncertainty.
- Confirm that the output bundle includes the source PDF, digitalized PDF, Korean PDF, page images, and page-level text artifacts needed for the public site.

## 2. Publish To Supabase

- Confirm that publish credentials are available locally:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`
- Publish one output:

```bash
python -m backend.publish --output-dir ./output/PaperName --name PaperName
```

- Preview a batch publish queue before writing anything:

```bash
python -m backend.publish --output-root ./output --dry-run
```

- Run the real batch publish only after reviewing the queue:

```bash
python -m backend.publish --output-root ./output
```

## 3. Validate Publish Artifacts

- Check the generated `*_publish_report.json` for:
  - `success`
  - `health_check`
  - `reason`
  - published `slug`
- Open the operations summary in Streamlit if a publish needs manual follow-up.
- Resolve metadata overrides before deploying if public presentation would otherwise look weak or misleading.

## 4. Deploy The Frontend

- Confirm that the Vercel project points at `frontend/`.
- Confirm that the live project has valid frontend read variables:
  - `NEXT_PUBLIC_SUPABASE_URL`
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- Deploy from the repository root so Vercel respects the configured root directory:

```bash
cmd /c vercel deploy --prod --yes
```

## 5. Run Production Smoke Checks

- Check the home page:
  - hero loads
  - recent documents render
  - no outage notice is present
- Check browse routes:
  - `/browse`
  - `/browse/author`
  - `/browse/era`
- Check at least one document detail route:
  - metadata panel
  - page rail
  - source image
  - original/Korean text
  - PDF download links
- If live data is unavailable, treat that as a release blocker unless the deployment was intentionally a shell-only fallback.

## 6. Lock The Repo State

- Run backend regression checks:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

- Run frontend regression/build checks:

```bash
cd frontend
npm run test
npm run build
```

- Commit and push the release-ready state so Git-backed Vercel deploys stay aligned with the successful local deploy.

## 7. Record The Change

- Update `CODEX_CHECKLIST.json` when priorities or blockers changed.
- Add a Notion `Dev Log` entry for changes that materially affect deployment, publishing, reliability, or operator workflow.
- If the release uncovered a new blocker, capture the exact failure mode and the next operator action instead of leaving a vague note.

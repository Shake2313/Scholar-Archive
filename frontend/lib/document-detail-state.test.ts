import { describe, expect, it } from "vitest";

import { buildDocumentViewerState } from "@/lib/document-detail-state";
import type { ArchiveDocument, ArchivePage } from "@/lib/types";

const document: ArchiveDocument = {
  id: 7,
  slug: "demo",
  title: "Demo Paper",
  author_display: "Demo Author",
  publication_year: 1912,
  century_label: "20th century",
  language: "English",
  journal_or_book: "Demo Journal",
  volume: "4",
  issue: "2",
  page_range: "10-22",
  doi: "10.1000/demo",
  summary: "Summary",
  storage_bucket: "archive",
  source_pdf_path: "pdf/source file.pdf",
  digitalized_pdf_path: "pdf/digitalized.pdf",
  korean_pdf_path: null,
  cover_image_path: null,
  page_count: 2,
  requested_page_count: 2,
  rights_assessment: "likely_public_domain",
  published_at: "2026-04-02T00:00:00Z",
  status: "published",
};

const pages: ArchivePage[] = [
  {
    id: 70,
    document_id: 7,
    page_number: 1,
    image_path: "images/page 001.png",
    digitalized_tex_path: "page_001.tex",
    digitalized_text: "Original text",
    korean_text: "번역문",
    structure_json_path: "page_001_structure.json",
  },
  {
    id: 71,
    document_id: 7,
    page_number: 2,
    image_path: null,
    digitalized_tex_path: "page_002.tex",
    digitalized_text: null,
    korean_text: null,
    structure_json_path: "page_002_structure.json",
  },
];

describe("document-detail-state", () => {
  it("builds viewer urls for downloads and page images", () => {
    const resolvePublicUrl = (bucket: string, storagePath: string | null) =>
      storagePath ? `https://cdn.example/${bucket}/${storagePath}` : null;

    const state = buildDocumentViewerState(document, pages, resolvePublicUrl);

    expect(state.sourcePdfUrl).toBe(
      "https://cdn.example/archive/pdf/source file.pdf",
    );
    expect(state.digitalizedPdfUrl).toBe(
      "https://cdn.example/archive/pdf/digitalized.pdf",
    );
    expect(state.koreanPdfUrl).toBeNull();
    expect(state.viewerPages).toEqual([
      expect.objectContaining({
        page_number: 1,
        imageUrl: "https://cdn.example/archive/images/page 001.png",
      }),
      expect.objectContaining({
        page_number: 2,
        imageUrl: null,
      }),
    ]);
  });
});

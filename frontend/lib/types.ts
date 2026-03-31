export type ArchiveDocument = {
  id: number;
  slug: string;
  title: string;
  author_display: string | null;
  publication_year: number | null;
  century_label: string | null;
  language: string | null;
  journal_or_book: string | null;
  volume: string | null;
  issue: string | null;
  page_range: string | null;
  doi: string | null;
  summary: string | null;
  storage_bucket: string;
  source_pdf_path: string | null;
  digitalized_pdf_path: string | null;
  korean_pdf_path: string | null;
  cover_image_path: string | null;
  page_count: number;
  requested_page_count: number;
  rights_assessment: string | null;
  published_at: string | null;
  status: string;
};

export type ArchivePage = {
  id: number;
  document_id: number;
  page_number: number;
  image_path: string | null;
  digitalized_tex_path: string | null;
  digitalized_text: string | null;
  korean_text: string | null;
  structure_json_path: string | null;
};

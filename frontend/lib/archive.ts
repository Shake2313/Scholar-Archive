import type { ArchiveDocument, ArchivePage } from "@/lib/types";
import { getSupabaseBaseUrl, getSupabaseReadClient } from "@/lib/supabase/server";

const documentSelect =
  "id,slug,title,author_display,publication_year,century_label,language,journal_or_book,volume,issue,page_range,doi,summary,storage_bucket,source_pdf_path,digitalized_pdf_path,korean_pdf_path,cover_image_path,page_count,requested_page_count,rights_assessment,published_at,status";

export function getStoragePublicUrl(
  bucket: string,
  storagePath: string | null,
): string | null {
  const base = getSupabaseBaseUrl();
  if (!storagePath || !base) {
    return null;
  }
  return `${base.replace(/\/$/, "")}/storage/v1/object/public/${encodeURIComponent(bucket)}/${storagePath
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/")}`;
}

export async function getRecentDocuments(limit = 6): Promise<ArchiveDocument[]> {
  const supabase = getSupabaseReadClient();
  if (!supabase) {
    return [];
  }
  const { data, error } = await supabase
    .from("documents")
    .select(documentSelect)
    .eq("status", "published")
    .order("published_at", { ascending: false, nullsFirst: false })
    .limit(limit);
  if (error) {
    throw new Error(error.message);
  }
  return (data ?? []) as ArchiveDocument[];
}

export async function getAllDocuments(): Promise<ArchiveDocument[]> {
  const supabase = getSupabaseReadClient();
  if (!supabase) {
    return [];
  }
  const { data, error } = await supabase
    .from("documents")
    .select(documentSelect)
    .eq("status", "published")
    .order("publication_year", { ascending: true, nullsFirst: false })
    .order("title", { ascending: true });
  if (error) {
    throw new Error(error.message);
  }
  return (data ?? []) as ArchiveDocument[];
}

export async function getDocumentBySlug(
  slug: string,
): Promise<ArchiveDocument | null> {
  const supabase = getSupabaseReadClient();
  if (!supabase) {
    return null;
  }
  const { data, error } = await supabase
    .from("documents")
    .select(documentSelect)
    .eq("slug", slug)
    .maybeSingle();
  if (error) {
    throw new Error(error.message);
  }
  return (data as ArchiveDocument | null) ?? null;
}

export async function getDocumentPages(
  documentId: number,
): Promise<ArchivePage[]> {
  const supabase = getSupabaseReadClient();
  if (!supabase) {
    return [];
  }
  const { data, error } = await supabase
    .from("document_pages")
    .select(
      "id,document_id,page_number,image_path,digitalized_tex_path,digitalized_text,korean_text,structure_json_path",
    )
    .eq("document_id", documentId)
    .order("page_number", { ascending: true });
  if (error) {
    throw new Error(error.message);
  }
  return (data ?? []) as ArchivePage[];
}

export function filterDocuments(
  documents: ArchiveDocument[],
  query: string,
): ArchiveDocument[] {
  const q = query.trim().toLowerCase();
  if (!q) {
    return documents;
  }
  return documents.filter((document) =>
    [document.title, document.author_display, document.journal_or_book, document.century_label]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(q)),
  );
}

export function groupDocumentsByCentury(documents: ArchiveDocument[]) {
  return documents.reduce<Record<string, ArchiveDocument[]>>((groups, document) => {
    const key = document.century_label ?? "Undated";
    groups[key] = groups[key] ?? [];
    groups[key].push(document);
    return groups;
  }, {});
}

export function groupDocumentsByAuthor(documents: ArchiveDocument[]) {
  return documents.reduce<Record<string, ArchiveDocument[]>>((groups, document) => {
    const key = document.author_display ?? "Unknown author";
    groups[key] = groups[key] ?? [];
    groups[key].push(document);
    return groups;
  }, {});
}

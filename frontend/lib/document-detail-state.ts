import { getStoragePublicUrl } from "@/lib/archive";
import type { ArchiveDocument, ArchivePage } from "@/lib/types";

export type ViewerPage = ArchivePage & {
  imageUrl: string | null;
};

export type DocumentViewerState = {
  sourcePdfUrl: string | null;
  digitalizedPdfUrl: string | null;
  koreanPdfUrl: string | null;
  viewerPages: ViewerPage[];
};

type PublicUrlResolver = (
  bucket: string,
  storagePath: string | null,
) => string | null;

export function buildDocumentViewerState(
  document: ArchiveDocument,
  pages: ArchivePage[],
  resolvePublicUrl: PublicUrlResolver = getStoragePublicUrl,
): DocumentViewerState {
  return {
    sourcePdfUrl: resolvePublicUrl(
      document.storage_bucket,
      document.source_pdf_path,
    ),
    digitalizedPdfUrl: resolvePublicUrl(
      document.storage_bucket,
      document.digitalized_pdf_path,
    ),
    koreanPdfUrl: resolvePublicUrl(
      document.storage_bucket,
      document.korean_pdf_path,
    ),
    viewerPages: pages.map((page) => ({
      ...page,
      imageUrl: resolvePublicUrl(document.storage_bucket, page.image_path),
    })),
  };
}

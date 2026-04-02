import { notFound } from "next/navigation";

import { DocumentViewer } from "@/components/document-viewer";
import {
  getDocumentBySlug,
  getDocumentPages,
} from "@/lib/archive";
import { buildDocumentViewerState } from "@/lib/document-detail-state";
import type { ArchiveDocument, ArchivePage } from "@/lib/types";

export const revalidate = 60;

export default async function DocumentDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  let archiveError: string | null = null;
  let document: ArchiveDocument | null = null;

  try {
    document = await getDocumentBySlug(slug);
  } catch (error) {
    console.error(`Failed to load document '${slug}'.`, error);
    archiveError =
      "The document record could not be loaded from the live archive backend.";
  }

  if (archiveError) {
    return (
      <div className="stack">
        <section className="noticePanel">
          <p className="eyebrow">Document</p>
          <h1>Archive data is temporarily unavailable</h1>
          <p>{archiveError}</p>
        </section>
      </div>
    );
  }

  if (!document) {
    notFound();
  }
  let pages: ArchivePage[] = [];

  try {
    pages = await getDocumentPages(document.id);
  } catch (error) {
    console.error(`Failed to load pages for document '${slug}'.`, error);
    return (
      <div className="stack">
        <section className="noticePanel">
          <p className="eyebrow">Document</p>
          <h1>Document pages are temporarily unavailable</h1>
          <p>
            The document record loaded, but the page-level source and
            translation data could not be fetched from the archive backend.
          </p>
        </section>
      </div>
    );
  }

  const viewerState = buildDocumentViewerState(document, pages);

  return (
    <DocumentViewer
      digitalizedPdfUrl={viewerState.digitalizedPdfUrl}
      document={document}
      koreanPdfUrl={viewerState.koreanPdfUrl}
      pages={viewerState.viewerPages}
      sourcePdfUrl={viewerState.sourcePdfUrl}
    />
  );
}

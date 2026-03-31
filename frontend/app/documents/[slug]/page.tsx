import { notFound } from "next/navigation";

import { DocumentViewer } from "@/components/document-viewer";
import {
  getDocumentBySlug,
  getDocumentPages,
  getStoragePublicUrl,
} from "@/lib/archive";

export const revalidate = 60;

export default async function DocumentDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const document = await getDocumentBySlug(slug);
  if (!document) {
    notFound();
  }
  const pages = (await getDocumentPages(document.id)).map((page) => ({
    ...page,
    imageUrl: getStoragePublicUrl(document.storage_bucket, page.image_path),
  }));

  return (
    <DocumentViewer
      digitalizedPdfUrl={getStoragePublicUrl(
        document.storage_bucket,
        document.digitalized_pdf_path,
      )}
      document={document}
      koreanPdfUrl={getStoragePublicUrl(
        document.storage_bucket,
        document.korean_pdf_path,
      )}
      pages={pages}
      sourcePdfUrl={getStoragePublicUrl(
        document.storage_bucket,
        document.source_pdf_path,
      )}
    />
  );
}

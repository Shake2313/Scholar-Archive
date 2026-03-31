import Link from "next/link";

import type { ArchiveDocument } from "@/lib/types";

export function DocumentCard({ document }: { document: ArchiveDocument }) {
  return (
    <article className="documentCard">
      <div className="documentCardMeta">
        <span>{document.century_label ?? "Undated"}</span>
        <span>{document.publication_year ?? "n.d."}</span>
      </div>
      <h3>
        <Link href={`/documents/${document.slug}`}>{document.title}</Link>
      </h3>
      <p>{document.author_display ?? "Unknown author"}</p>
      <p className="documentCardSecondary">
        {document.journal_or_book ?? "Independent manuscript"}
      </p>
    </article>
  );
}

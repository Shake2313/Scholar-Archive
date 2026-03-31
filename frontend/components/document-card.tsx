import Link from "next/link";

import { getRightsLabel } from "@/lib/archive-utils";
import type { ArchiveDocument } from "@/lib/types";

export function DocumentCard({ document }: { document: ArchiveDocument }) {
  return (
    <article className="documentCard">
      <div className="documentPillRow">
        <span className="documentPill">{document.century_label ?? "Undated"}</span>
        <span className="documentPill">{document.publication_year ?? "n.d."}</span>
        <span className="documentPill">{getRightsLabel(document.rights_assessment)}</span>
      </div>
      <h3>
        <Link href={`/documents/${document.slug}`}>{document.title}</Link>
      </h3>
      <p>{document.author_display ?? "Unknown author"}</p>
      <p className="documentCardSecondary">
        {document.journal_or_book ?? "Independent manuscript"}
      </p>
      <div className="documentCardFooter">
        <span>{document.language ?? "Language unknown"}</span>
        <span>{document.page_count} pages</span>
      </div>
    </article>
  );
}

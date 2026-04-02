import Link from "next/link";

import { getRightsLabel } from "@/lib/archive-utils";
import type { ArchiveDocument } from "@/lib/types";

export function DocumentCard({ document }: { document: ArchiveDocument }) {
  const publicationLabel = document.publication_year ?? "n.d.";
  const collectionLabel = document.journal_or_book ?? "Independent manuscript";
  const citationParts = [document.volume && `Vol. ${document.volume}`, document.issue && `No. ${document.issue}`]
    .filter(Boolean)
    .join(" · ");

  return (
    <article className="documentCard">
      <div className="documentPillRow">
        <span className="documentPill">{document.century_label ?? "Undated"}</span>
        <span className="documentPill">{publicationLabel}</span>
        <span className="documentPill">{getRightsLabel(document.rights_assessment)}</span>
      </div>
      <h3>
        <Link href={`/documents/${document.slug}`}>{document.title}</Link>
      </h3>
      <p>{document.author_display ?? "Unknown author"}</p>
      <p className="documentCardSecondary">{collectionLabel}</p>
      {citationParts || document.page_range || document.doi ? (
        <dl className="documentMetaList">
          {citationParts ? (
            <div className="documentMetaRow">
              <dt>Edition</dt>
              <dd>{citationParts}</dd>
            </div>
          ) : null}
          {document.page_range ? (
            <div className="documentMetaRow">
              <dt>Pages</dt>
              <dd>{document.page_range}</dd>
            </div>
          ) : null}
          {document.doi ? (
            <div className="documentMetaRow">
              <dt>DOI</dt>
              <dd>{document.doi}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}
      <div className="documentCardFooter">
        <span>{document.language ?? "Language unknown"}</span>
        <span>{document.page_count} pages</span>
      </div>
    </article>
  );
}

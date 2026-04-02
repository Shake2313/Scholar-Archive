import { CatalogFilters } from "@/components/catalog-filters";
import { DocumentCard } from "@/components/document-card";
import { getAllDocuments, groupDocumentsByAuthor } from "@/lib/archive";
import {
  buildBrowseCatalogState,
  type BrowseSearchParams,
} from "@/lib/browse-state";
import type { ArchiveDocument } from "@/lib/types";

export const revalidate = 60;

export default async function BrowseByAuthorPage({
  searchParams,
}: {
  searchParams?: Promise<BrowseSearchParams>;
}) {
  const params = (await searchParams) ?? {};
  let archiveError: string | null = null;
  let allDocuments: ArchiveDocument[] = [];

  try {
    allDocuments = await getAllDocuments();
  } catch (error) {
    console.error("Failed to load archive data for browse by author.", error);
    archiveError =
      "The author view could not load live data from Supabase for this request.";
  }
  const { filteredDocuments: documents, languageOptions, values } =
    buildBrowseCatalogState(allDocuments, params);
  const groups = groupDocumentsByAuthor(documents);
  const authors = Object.keys(groups).sort((a, b) => a.localeCompare(b));

  return (
    <div className="stack">
      <section className="sectionPanel">
        <p className="eyebrow">Browse</p>
        <h1>By Author</h1>
        <p className="sectionLead">
          Public entries grouped by normalized author metadata after the current
          catalog filters are applied.
        </p>
        <CatalogFilters
          idPrefix="author"
          languageOptions={languageOptions}
          resetHref="/browse/author"
          values={values}
        />
      </section>

      {archiveError ? (
        <section className="noticePanel">
          <h2>Archive data is temporarily unavailable</h2>
          <p>{archiveError}</p>
        </section>
      ) : null}

      {authors.map((author) => (
        <section className="sectionPanel" key={author}>
          <div className="sectionHeader">
            <div>
              <p className="eyebrow">Author</p>
              <h2>{author}</h2>
            </div>
            <span className="countBadge">{groups[author].length} documents</span>
          </div>
          <div className="cardGrid">
            {groups[author].map((document) => (
              <DocumentCard document={document} key={document.id} />
            ))}
          </div>
        </section>
      ))}

      {documents.length === 0 && !archiveError ? (
        <section className="emptyState">No documents match the current filter.</section>
      ) : null}
    </div>
  );
}

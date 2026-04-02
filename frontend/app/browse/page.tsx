import { CatalogFilters } from "@/components/catalog-filters";
import { DocumentCard } from "@/components/document-card";
import { getAllDocuments } from "@/lib/archive";
import {
  buildBrowseCatalogState,
  type BrowseSearchParams,
} from "@/lib/browse-state";
import type { ArchiveDocument } from "@/lib/types";

export const revalidate = 60;

export default async function BrowsePage({
  searchParams,
}: {
  searchParams?: Promise<BrowseSearchParams>;
}) {
  const params = (await searchParams) ?? {};

  let archiveError: string | null = null;
  let documents: ArchiveDocument[] = [];

  try {
    documents = await getAllDocuments();
  } catch (error) {
    console.error("Failed to load archive catalog.", error);
    archiveError =
      "The catalog could not load live data from Supabase for this request.";
  }
  const { filteredDocuments, languageOptions, overview, values } =
    buildBrowseCatalogState(documents, params);

  return (
    <div className="stack">
      <section className="sectionPanel">
        <p className="eyebrow">Catalog</p>
        <h1>Browse the public archive</h1>
        <p className="sectionLead">
          Search across titles, authors, journals, languages, publication
          years, volume and issue metadata, and rights signals from the
          published collection.
        </p>

        <CatalogFilters
          idPrefix="catalog"
          languageOptions={languageOptions}
          resetHref="/browse"
          values={values}
        />
      </section>

      <section className="sectionPanel">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Collection state</p>
            <h2>
              {filteredDocuments.length} visible of {overview.documentCount}{" "}
              published entries
            </h2>
          </div>
        </div>
        <div className="statsGrid">
          <div className="statCard">
            <span className="statValue">{overview.authorCount}</span>
            <span className="statLabel">Authors</span>
          </div>
          <div className="statCard">
            <span className="statValue">{overview.centuryCount}</span>
            <span className="statLabel">Centuries</span>
          </div>
          <div className="statCard">
            <span className="statValue">{overview.languageCount}</span>
            <span className="statLabel">Languages</span>
          </div>
          <div className="statCard">
            <span className="statValue">{overview.publicDomainCount}</span>
            <span className="statLabel">Likely public domain</span>
          </div>
        </div>
      </section>

      <section className="sectionPanel">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Results</p>
            <h2>Catalog results</h2>
          </div>
        </div>
        {archiveError ? (
          <div className="noticePanel">
            <h3>Archive data is temporarily unavailable</h3>
            <p>{archiveError}</p>
          </div>
        ) : null}
        <div className="cardGrid">
          {filteredDocuments.map((document) => (
            <DocumentCard document={document} key={document.id} />
          ))}
        </div>
        {filteredDocuments.length === 0 && !archiveError ? (
          <div className="emptyState">
            No documents match the current search. Try a broader query or clear
            one of the filters.
          </div>
        ) : null}
      </section>
    </div>
  );
}

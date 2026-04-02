import { CatalogFilters } from "@/components/catalog-filters";
import { DocumentCard } from "@/components/document-card";
import {
  buildEraSections,
  getAllDocuments,
} from "@/lib/archive";
import {
  buildBrowseCatalogState,
  type BrowseSearchParams,
} from "@/lib/browse-state";
import type { ArchiveDocument } from "@/lib/types";

export const revalidate = 60;

export default async function BrowseByEraPage({
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
    console.error("Failed to load archive data for browse by era.", error);
    archiveError =
      "The era view could not load live data from Supabase for this request.";
  }
  const { filteredDocuments: documents, languageOptions, overview, values } =
    buildBrowseCatalogState(allDocuments, params);
  const eraSections = buildEraSections(documents, values.sort);

  return (
    <div className="stack">
      <section className="sectionPanel">
        <p className="eyebrow">Browse</p>
        <h1>By Era</h1>
        <p className="sectionLead">
          Grouped by publication year and derived century labels after the
          current catalog filters are applied.
        </p>
        <CatalogFilters
          idPrefix="era"
          languageOptions={languageOptions}
          resetHref="/browse/era"
          values={values}
        />
      </section>

      {archiveError ? (
        <section className="noticePanel">
          <h2>Archive data is temporarily unavailable</h2>
          <p>{archiveError}</p>
        </section>
      ) : null}

      {documents.length > 0 ? (
        <section className="sectionPanel">
          <div className="sectionHeader">
            <div>
              <p className="eyebrow">Timeline overview</p>
              <h2>Browse the archive by century and exact year</h2>
            </div>
            <span className="countBadge">
              {overview.documentCount} documents across {overview.centuryCount} centuries
            </span>
          </div>
          <div className="statsGrid">
            <div className="statCard">
              <span className="statValue">
                {overview.earliestYear && overview.latestYear
                  ? `${overview.earliestYear}-${overview.latestYear}`
                  : "Undated"}
              </span>
              <span className="statLabel">Year span</span>
            </div>
            <div className="statCard">
              <span className="statValue">{overview.centuryCount}</span>
              <span className="statLabel">Century sections</span>
            </div>
            <div className="statCard">
              <span className="statValue">
                {eraSections.reduce((total, section) => total + section.yearBuckets.length, 0)}
              </span>
              <span className="statLabel">Year buckets</span>
            </div>
          </div>
          <div className="timelineNav">
            {eraSections.map((section) => (
              <a className="timelineNavLink" href={`#${section.id}`} key={section.id}>
                <span>{section.label}</span>
                <small>{section.documentCount}</small>
              </a>
            ))}
          </div>
        </section>
      ) : null}

      {eraSections.map((section) => (
        <section className="sectionPanel eraSection" id={section.id} key={section.id}>
          <div className="sectionHeader">
            <div>
              <p className="eyebrow">Era</p>
              <h2>{section.label}</h2>
            </div>
            <div className="eraSectionMeta">
              <span className="countBadge">{section.documentCount} documents</span>
              <span className="countBadge">{section.yearRangeLabel}</span>
            </div>
          </div>
          <div className="yearBucketList">
            {section.yearBuckets.map((bucket) => (
              <div className="yearBucket" key={`${section.id}-${bucket.label}`}>
                <div className="yearBucketHeader">
                  <div>
                    <p className="eyebrow">Year bucket</p>
                    <h3>{bucket.label}</h3>
                  </div>
                  <span className="countBadge">{bucket.count} documents</span>
                </div>
                <div className="cardGrid">
                  {bucket.documents.map((document) => (
                    <DocumentCard document={document} key={document.id} />
                  ))}
                </div>
              </div>
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

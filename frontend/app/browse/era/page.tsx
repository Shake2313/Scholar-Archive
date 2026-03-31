import { DocumentCard } from "@/components/document-card";
import {
  applyDocumentFilters,
  buildEraSections,
  getAllDocuments,
  getArchiveOverview,
  getLanguageOptions,
  normalizeBrowseSort,
  sortDocuments,
} from "@/lib/archive";

export const revalidate = 60;

function readParam(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function BrowseByEraPage({
  searchParams,
}: {
  searchParams?: Promise<{
    q?: string | string[];
    language?: string | string[];
    rights?: string | string[];
    sort?: string | string[];
  }>;
}) {
  const params = (await searchParams) ?? {};
  const query = readParam(params.q);
  const language = readParam(params.language);
  const rights = readParam(params.rights);
  const sort = normalizeBrowseSort(readParam(params.sort));
  const allDocuments = await getAllDocuments();
  const languageOptions = getLanguageOptions(allDocuments);
  const documents = sortDocuments(
    applyDocumentFilters(allDocuments, {
      query,
      language,
      rights,
    }),
    sort,
  );
  const overview = getArchiveOverview(documents);
  const eraSections = buildEraSections(documents, sort);

  return (
    <div className="stack">
      <section className="sectionPanel">
        <p className="eyebrow">Browse</p>
        <h1>By Era</h1>
        <p className="sectionLead">
          Grouped by publication year and derived century labels after the
          current catalog filters are applied.
        </p>
        <form className="catalogFilters" method="get">
          <div className="catalogFilterField catalogFilterFieldWide">
            <label htmlFor="era-query">Search</label>
            <input
              defaultValue={query}
              id="era-query"
              name="q"
              placeholder="Search title, author, journal, or century"
            />
          </div>
          <div className="catalogFilterField">
            <label htmlFor="era-sort">Sort</label>
            <select defaultValue={sort} id="era-sort" name="sort">
              <option value="recent">Most recent</option>
              <option value="oldest">Oldest publication year</option>
              <option value="title">Title A-Z</option>
            </select>
          </div>
          <div className="catalogFilterField">
            <label htmlFor="era-language">Language</label>
            <select defaultValue={language} id="era-language" name="language">
              <option value="">All languages</option>
              {languageOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div className="catalogFilterField">
            <label htmlFor="era-rights">Rights</label>
            <select defaultValue={rights} id="era-rights" name="rights">
              <option value="">All rights signals</option>
              <option value="public_domain">Likely public domain</option>
              <option value="undetermined">Rights uncertain</option>
            </select>
          </div>
          <div className="catalogFilterActions">
            <button type="submit">Apply filters</button>
          </div>
        </form>
      </section>

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

      {documents.length === 0 ? (
        <section className="emptyState">No documents match the current filter.</section>
      ) : null}
    </div>
  );
}

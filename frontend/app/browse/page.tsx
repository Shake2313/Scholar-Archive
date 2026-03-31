import { DocumentCard } from "@/components/document-card";
import {
  applyDocumentFilters,
  getAllDocuments,
  getArchiveOverview,
  getLanguageOptions,
  normalizeBrowseSort,
  sortDocuments,
} from "@/lib/archive";

export const revalidate = 60;

function readParam(
  value: string | string[] | undefined,
): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function BrowsePage({
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

  const documents = await getAllDocuments();
  const languageOptions = getLanguageOptions(documents);
  const filteredDocuments = sortDocuments(
    applyDocumentFilters(documents, {
      query,
      language,
      rights,
    }),
    sort,
  );
  const overview = getArchiveOverview(documents);

  return (
    <div className="stack">
      <section className="sectionPanel">
        <p className="eyebrow">Catalog</p>
        <h1>Browse the public archive</h1>
        <p className="sectionLead">
          Search across titles, authors, journals, languages, publication
          years, and rights signals from the published collection.
        </p>

        <form className="catalogFilters" method="get">
          <div className="catalogFilterField catalogFilterFieldWide">
            <label htmlFor="catalog-query">Search</label>
            <input
              defaultValue={query}
              id="catalog-query"
              name="q"
              placeholder="Title, author, journal, year, or century"
            />
          </div>
          <div className="catalogFilterField">
            <label htmlFor="catalog-sort">Sort</label>
            <select defaultValue={sort} id="catalog-sort" name="sort">
              <option value="recent">Most recent</option>
              <option value="oldest">Oldest publication year</option>
              <option value="title">Title A-Z</option>
            </select>
          </div>
          <div className="catalogFilterField">
            <label htmlFor="catalog-language">Language</label>
            <select
              defaultValue={language}
              id="catalog-language"
              name="language"
            >
              <option value="">All languages</option>
              {languageOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div className="catalogFilterField">
            <label htmlFor="catalog-rights">Rights</label>
            <select defaultValue={rights} id="catalog-rights" name="rights">
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
        <div className="cardGrid">
          {filteredDocuments.map((document) => (
            <DocumentCard document={document} key={document.id} />
          ))}
        </div>
        {filteredDocuments.length === 0 ? (
          <div className="emptyState">
            No documents match the current search. Try a broader query or clear
            one of the filters.
          </div>
        ) : null}
      </section>
    </div>
  );
}

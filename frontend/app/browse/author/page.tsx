import { DocumentCard } from "@/components/document-card";
import {
  applyDocumentFilters,
  getAllDocuments,
  getLanguageOptions,
  groupDocumentsByAuthor,
  normalizeBrowseSort,
  sortDocuments,
} from "@/lib/archive";

export const revalidate = 60;

function readParam(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function BrowseByAuthorPage({
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
        <form className="catalogFilters" method="get">
          <div className="catalogFilterField catalogFilterFieldWide">
            <label htmlFor="author-query">Search</label>
            <input
              defaultValue={query}
              id="author-query"
              name="q"
              placeholder="Search title, author, journal, or century"
            />
          </div>
          <div className="catalogFilterField">
            <label htmlFor="author-sort">Sort</label>
            <select defaultValue={sort} id="author-sort" name="sort">
              <option value="recent">Most recent</option>
              <option value="oldest">Oldest publication year</option>
              <option value="title">Title A-Z</option>
            </select>
          </div>
          <div className="catalogFilterField">
            <label htmlFor="author-language">Language</label>
            <select
              defaultValue={language}
              id="author-language"
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
            <label htmlFor="author-rights">Rights</label>
            <select defaultValue={rights} id="author-rights" name="rights">
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

      {documents.length === 0 ? (
        <section className="emptyState">No documents match the current filter.</section>
      ) : null}
    </div>
  );
}

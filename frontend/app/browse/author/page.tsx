import { DocumentCard } from "@/components/document-card";
import { filterDocuments, getAllDocuments, groupDocumentsByAuthor } from "@/lib/archive";

export const revalidate = 60;

export default async function BrowseByAuthorPage({
  searchParams,
}: {
  searchParams?: Promise<{ q?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const query = params.q ?? "";
  const documents = filterDocuments(await getAllDocuments(), query);
  const groups = groupDocumentsByAuthor(documents);
  const authors = Object.keys(groups).sort((a, b) => a.localeCompare(b));

  return (
    <div className="stack">
      <section className="sectionPanel">
        <p className="eyebrow">Browse</p>
        <h1>By Author</h1>
        <p className="sectionLead">
          Public entries grouped by normalized document author metadata.
        </p>
        <form className="searchBar" method="get">
          <input defaultValue={query} name="q" placeholder="Search title, author, journal..." />
          <button type="submit">Search</button>
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

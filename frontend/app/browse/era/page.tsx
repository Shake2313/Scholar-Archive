import { DocumentCard } from "@/components/document-card";
import { filterDocuments, getAllDocuments, groupDocumentsByCentury } from "@/lib/archive";

export const revalidate = 60;

export default async function BrowseByEraPage({
  searchParams,
}: {
  searchParams?: Promise<{ q?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const query = params.q ?? "";
  const documents = filterDocuments(await getAllDocuments(), query);
  const groups = groupDocumentsByCentury(documents);
  const centuries = Object.keys(groups).sort();

  return (
    <div className="stack">
      <section className="sectionPanel">
        <p className="eyebrow">Browse</p>
        <h1>By Era</h1>
        <p className="sectionLead">
          Grouped by publication year and derived century label.
        </p>
        <form className="searchBar" method="get">
          <input defaultValue={query} name="q" placeholder="Search title, author, journal..." />
          <button type="submit">Search</button>
        </form>
      </section>

      {centuries.map((century) => (
        <section className="sectionPanel" key={century}>
          <div className="sectionHeader">
            <div>
              <p className="eyebrow">Era</p>
              <h2>{century}</h2>
            </div>
            <span className="countBadge">{groups[century].length} documents</span>
          </div>
          <div className="cardGrid">
            {groups[century].map((document) => (
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

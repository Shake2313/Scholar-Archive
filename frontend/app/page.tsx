import Link from "next/link";

import { DocumentCard } from "@/components/document-card";
import {
  getAllDocuments,
  getArchiveOverview,
  getRecentDocuments,
  getTopAuthors,
  getTopCenturies,
} from "@/lib/archive";
import { isSupabaseConfigured } from "@/lib/supabase/server";
import type { ArchiveDocument } from "@/lib/types";

export const revalidate = 60;

export default async function HomePage() {
  let archiveError: string | null = null;
  let allDocuments: ArchiveDocument[] = [];
  let recentDocuments: ArchiveDocument[] = [];

  try {
    [allDocuments, recentDocuments] = await Promise.all([
      getAllDocuments(),
      getRecentDocuments(6),
    ]);
  } catch (error) {
    console.error("Failed to load archive data for the home page.", error);
    archiveError =
      "The live archive could not reach Supabase during the latest data fetch.";
  }

  const overview = getArchiveOverview(allDocuments);
  const topAuthors = getTopAuthors(allDocuments, 5);
  const topCenturies = getTopCenturies(allDocuments, 5);

  return (
    <div className="stack">
      <section className="heroPanel heroPanelWide">
        <div className="heroCopyBlock">
          <p className="eyebrow">Public archive</p>
          <h1>Scholar Archive</h1>
          <p className="heroCopy">
            A reading surface for digitized historical papers, source scans,
            and Korean translations published from the Scholar Archive pipeline.
          </p>
          <form action="/browse" className="searchBar searchBarWide">
            <input
              name="q"
              placeholder="Search title, author, year, journal, or century..."
            />
            <button type="submit">Search archive</button>
          </form>
        </div>

        <div className="heroAside">
          <div className="heroActions">
            <Link className="primaryLink" href="/browse">
              Open catalog
            </Link>
            <Link className="secondaryLink" href="/browse/era">
              Browse by era
            </Link>
            <Link className="secondaryLink" href="/browse/author">
              Browse by author
            </Link>
          </div>
          <div className="statsGrid">
            <div className="statCard">
              <span className="statValue">{overview.documentCount}</span>
              <span className="statLabel">Published documents</span>
            </div>
            <div className="statCard">
              <span className="statValue">{overview.authorCount}</span>
              <span className="statLabel">Distinct authors</span>
            </div>
            <div className="statCard">
              <span className="statValue">{overview.centuryCount}</span>
              <span className="statLabel">Century groupings</span>
            </div>
            <div className="statCard">
              <span className="statValue">
                {overview.earliestYear && overview.latestYear
                  ? `${overview.earliestYear}-${overview.latestYear}`
                  : "Undated"}
              </span>
              <span className="statLabel">Publication span</span>
            </div>
          </div>
        </div>
      </section>

      {!isSupabaseConfigured() ? (
        <section className="noticePanel">
          <h2>Supabase is not configured</h2>
          <p>
            Set <code>NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
            <code>NEXT_PUBLIC_SUPABASE_ANON_KEY</code>, or provide server-side{" "}
            <code>SUPABASE_URL</code> with{" "}
            <code>SUPABASE_SERVICE_ROLE_KEY</code> /{" "}
            <code>SUPABASE_SECRET_KEY</code>, to render live archive data.
          </p>
        </section>
      ) : null}

      {archiveError ? (
        <section className="noticePanel">
          <h2>Archive data is temporarily unavailable</h2>
          <p>
            {archiveError} The shell is online, but live catalog data could not
            be loaded for this request.
          </p>
        </section>
      ) : null}

      <section className="sectionPanel">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Entry points</p>
            <h2>Start from the shape of the archive</h2>
          </div>
        </div>
        <div className="entryGrid">
          <Link className="entryCard" href="/browse">
            <p className="eyebrow">Catalog</p>
            <h3>Search everything</h3>
            <p>
              Filter by language, rights signal, and sort order across the full
              public collection.
            </p>
          </Link>
          <Link className="entryCard" href="/browse/era">
            <p className="eyebrow">By Era</p>
            <h3>Trace publication periods</h3>
            <p>
              Follow the collection through century labels and publication
              years.
            </p>
          </Link>
          <Link className="entryCard" href="/browse/author">
            <p className="eyebrow">By Author</p>
            <h3>Move through author clusters</h3>
            <p>
              Browse the archive through normalized author metadata and repeat
              appearances.
            </p>
          </Link>
        </div>
      </section>

      <section className="spotlightGrid">
        <section className="sectionPanel">
          <div className="sectionHeader">
            <div>
              <p className="eyebrow">Top Eras</p>
              <h2>Century clusters</h2>
            </div>
          </div>
          <div className="facetList">
            {topCenturies.map((facet) => (
              <Link
                className="facetRow"
                href={`/browse/era?q=${encodeURIComponent(facet.label)}`}
                key={facet.label}
              >
                <span>{facet.label}</span>
                <span>{facet.count}</span>
              </Link>
            ))}
            {topCenturies.length === 0 ? (
              <div className="emptyState compactEmptyState">No era data yet.</div>
            ) : null}
          </div>
        </section>

        <section className="sectionPanel">
          <div className="sectionHeader">
            <div>
              <p className="eyebrow">Top Authors</p>
              <h2>Frequent names in the archive</h2>
            </div>
          </div>
          <div className="facetList">
            {topAuthors.map((facet) => (
              <Link
                className="facetRow"
                href={`/browse/author?q=${encodeURIComponent(facet.label)}`}
                key={facet.label}
              >
                <span>{facet.label}</span>
                <span>{facet.count}</span>
              </Link>
            ))}
            {topAuthors.length === 0 ? (
              <div className="emptyState compactEmptyState">No author data yet.</div>
            ) : null}
          </div>
        </section>
      </section>

      <section className="sectionPanel">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Recently published</p>
            <h2>Latest archive entries</h2>
          </div>
        </div>
        <div className="cardGrid">
          {recentDocuments.map((document) => (
            <DocumentCard document={document} key={document.id} />
          ))}
          {recentDocuments.length === 0 && !archiveError ? (
            <div className="emptyState">
              No published documents yet. Once the pipeline publishes a run,
              entries will appear here automatically.
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

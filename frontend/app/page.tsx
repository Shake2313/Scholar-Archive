import Link from "next/link";

import { DocumentCard } from "@/components/document-card";
import {
  getAllDocuments,
  getArchiveOverview,
  getRecentDocuments,
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
      getRecentDocuments(3),
    ]);
  } catch (error) {
    console.error("Failed to load archive data for the home page.", error);
    archiveError =
      "The live archive could not reach Supabase during the latest data fetch.";
  }

  const overview = getArchiveOverview(allDocuments);
  const publicationSpan =
    overview.earliestYear && overview.latestYear
      ? `${overview.earliestYear}-${overview.latestYear}`
      : "Undated";

  return (
    <div className="stack">
      <section className="heroPanel heroPanelWide">
        <div className="heroCopyBlock">
          <p className="eyebrow">Public archive</p>
          <h1>Scholar Archive</h1>
          <p className="heroCopy">
            A public reading surface for restored historical papers, source
            scans, and Korean translations.
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
          <div className="heroStatStrip">
            <div className="heroStatChip">
              <strong>{overview.documentCount}</strong>
              <span>Published documents</span>
            </div>
            <div className="heroStatChip">
              <strong>{overview.authorCount}</strong>
              <span>Distinct authors</span>
            </div>
            <div className="heroStatChip">
              <strong>{publicationSpan}</strong>
              <span>Publication span</span>
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
            <p className="eyebrow">Start reading</p>
            <h2>Recent entries</h2>
          </div>
          <Link className="secondaryLink" href="/browse">
            See full catalog
          </Link>
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

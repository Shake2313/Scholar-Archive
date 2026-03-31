import Link from "next/link";

import { DocumentCard } from "@/components/document-card";
import { getRecentDocuments } from "@/lib/archive";
import { isSupabaseConfigured } from "@/lib/supabase/server";

export const revalidate = 60;

export default async function HomePage() {
  const recentDocuments = await getRecentDocuments(6);

  return (
    <div className="stack">
      <section className="heroPanel">
        <div>
          <p className="eyebrow">Public archive</p>
          <h1>Scholar Archive</h1>
          <p className="heroCopy">
            A publication surface for digitized historical papers, source scans,
            and Korean translations produced by the pipeline.
          </p>
        </div>
        <div className="heroActions">
          <Link className="primaryLink" href="/browse/era">
            Browse by era
          </Link>
          <Link className="secondaryLink" href="/browse/author">
            Browse by author
          </Link>
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
          {recentDocuments.length === 0 ? (
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

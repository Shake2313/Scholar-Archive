"use client";

import { useMemo, useState } from "react";

import type { ArchiveDocument, ArchivePage } from "@/lib/types";

type PageWithUrls = ArchivePage & {
  imageUrl: string | null;
};

export function DocumentViewer({
  document,
  pages,
  sourcePdfUrl,
  digitalizedPdfUrl,
  koreanPdfUrl,
}: {
  document: ArchiveDocument;
  pages: PageWithUrls[];
  sourcePdfUrl: string | null;
  digitalizedPdfUrl: string | null;
  koreanPdfUrl: string | null;
}) {
  const [pageIndex, setPageIndex] = useState(0);
  const [tab, setTab] = useState<"digitalized" | "korean">("digitalized");
  const currentPage = pages[pageIndex] ?? null;
  const pageText = useMemo(() => {
    if (!currentPage) {
      return "";
    }
    return tab === "digitalized"
      ? currentPage.digitalized_text ?? ""
      : currentPage.korean_text ?? "";
  }, [currentPage, tab]);

  return (
    <div className="viewerShell">
      <aside className="viewerSidebar">
        <div className="viewerSidebarCard">
          <p className="eyebrow">Document</p>
          <h1>{document.title}</h1>
          <dl className="metadataGrid">
            <div>
              <dt>Author</dt>
              <dd>{document.author_display ?? "Unknown author"}</dd>
            </div>
            <div>
              <dt>Publication</dt>
              <dd>{document.publication_year ?? "n.d."}</dd>
            </div>
            <div>
              <dt>Collection</dt>
              <dd>{document.journal_or_book ?? "Independent manuscript"}</dd>
            </div>
            <div>
              <dt>Pages</dt>
              <dd>
                {document.page_count} / {document.requested_page_count}
              </dd>
            </div>
          </dl>
        </div>

        <div className="viewerSidebarCard">
          <p className="eyebrow">Downloads</p>
          <div className="downloadList">
            {sourcePdfUrl ? (
              <a href={sourcePdfUrl} target="_blank" rel="noreferrer">
                Original PDF
              </a>
            ) : null}
            {digitalizedPdfUrl ? (
              <a href={digitalizedPdfUrl} target="_blank" rel="noreferrer">
                Digitalized PDF
              </a>
            ) : null}
            {koreanPdfUrl ? (
              <a href={koreanPdfUrl} target="_blank" rel="noreferrer">
                Korean PDF
              </a>
            ) : null}
          </div>
        </div>

        <div className="viewerSidebarCard">
          <p className="eyebrow">Pages</p>
          <div className="pageIndexList">
            {pages.map((page, index) => (
              <button
                className={index === pageIndex ? "pageIndexButton isActive" : "pageIndexButton"}
                key={page.page_number}
                onClick={() => setPageIndex(index)}
                type="button"
              >
                Page {page.page_number}
              </button>
            ))}
          </div>
        </div>
      </aside>

      <section className="viewerMain">
        <div className="viewerToolbar">
          <div className="tabGroup">
            <button
              className={tab === "digitalized" ? "tabButton isActive" : "tabButton"}
              onClick={() => setTab("digitalized")}
              type="button"
            >
              Digitalized text
            </button>
            <button
              className={tab === "korean" ? "tabButton isActive" : "tabButton"}
              onClick={() => setTab("korean")}
              type="button"
            >
              Korean translation
            </button>
          </div>
          <span className="viewerPageLabel">
            {currentPage ? `Page ${currentPage.page_number}` : "No pages"}
          </span>
        </div>

        <div className="viewerPanels">
          <div className="viewerImagePanel">
            {currentPage?.imageUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img alt={`Source page ${currentPage.page_number}`} src={currentPage.imageUrl} />
            ) : (
              <div className="placeholderCard">No page image available.</div>
            )}
          </div>
          <div className="viewerTextPanel">
            <pre>{pageText || "No extracted text available for this page."}</pre>
          </div>
        </div>
      </section>
    </div>
  );
}

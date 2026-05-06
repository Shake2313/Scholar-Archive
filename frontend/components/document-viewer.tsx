"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { getRightsLabel } from "@/lib/archive-utils";
import type { ArchiveDocument, ArchivePage } from "@/lib/types";

type PageWithUrls = ArchivePage & {
  imageUrl: string | null;
};

type ReadingMode = "digitalized" | "korean" | "parallel";

function summarizePageText(page: ArchivePage): string {
  const text = (page.digitalized_text ?? page.korean_text ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) {
    return "No extracted text available.";
  }
  return text.length > 140 ? `${text.slice(0, 137).trimEnd()}...` : text;
}

function pageAvailabilityLabel(page: ArchivePage | null): string {
  if (!page) {
    return "No page selected";
  }
  const hasOriginal = Boolean(page.digitalized_text?.trim());
  const hasTranslation = Boolean(page.korean_text?.trim());
  if (hasOriginal && hasTranslation) {
    return "Original + Korean";
  }
  if (hasOriginal) {
    return "Original only";
  }
  if (hasTranslation) {
    return "Korean only";
  }
  return "Image only";
}

function TextPanel({
  title,
  eyebrow,
  body,
}: {
  title: string;
  eyebrow: string;
  body: string;
}) {
  return (
    <article className="viewerTextCard">
      <header className="viewerTextCardHeader">
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
      </header>
      <div className="viewerTextCardBody">
        <pre>{body || "No extracted text available for this page."}</pre>
      </div>
    </article>
  );
}

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
  const [readingMode, setReadingMode] = useState<ReadingMode>("parallel");
  const [imageZoom, setImageZoom] = useState<"fit" | "detail">("fit");
  const imagePanelRef = useRef<HTMLDivElement | null>(null);
  const textPanelRef = useRef<HTMLDivElement | null>(null);

  const currentPage = pages[pageIndex] ?? null;
  const currentPageNumber = currentPage?.page_number ?? null;
  const pageCount = pages.length;
  const currentOrdinal = pageCount > 0 ? pageIndex + 1 : 0;
  const rightsLabel = getRightsLabel(document.rights_assessment);

  const currentTexts = useMemo(
    () => ({
      digitalized: currentPage?.digitalized_text?.trim() ?? "",
      korean: currentPage?.korean_text?.trim() ?? "",
    }),
    [currentPage],
  );

  useEffect(() => {
    imagePanelRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    textPanelRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [pageIndex]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) {
        return;
      }
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName;
      if (tagName === "INPUT" || tagName === "TEXTAREA" || tagName === "SELECT") {
        return;
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setPageIndex((index) => Math.max(index - 1, 0));
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setPageIndex((index) => Math.min(index + 1, pageCount - 1));
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [pageCount]);

  return (
    <div className="viewerShell">
      <aside className="viewerSidebar">
        <div className="viewerSidebarCard">
          <Link className="viewerBackLink" href="/browse">
            Back to catalog
          </Link>
          <p className="eyebrow">Document</p>
          <h1>{document.title}</h1>
          {document.summary ? (
            <p className="viewerSummary">{document.summary}</p>
          ) : null}
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
              <dt>Century</dt>
              <dd>{document.century_label ?? "Undated"}</dd>
            </div>
            <div>
              <dt>Language</dt>
              <dd>{document.language ?? "Unknown"}</dd>
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
            {document.page_range ? (
              <div>
                <dt>Page range</dt>
                <dd>{document.page_range}</dd>
              </div>
            ) : null}
            {document.doi ? (
              <div>
                <dt>DOI</dt>
                <dd>{document.doi}</dd>
              </div>
            ) : null}
          </dl>

          <div
            className={
              rightsLabel === "Likely public domain" ? "rightsOk" : "rightsWarning"
            }
            style={{ marginTop: 14 }}
          >
            <strong>{rightsLabel}</strong>
            {rightsLabel !== "Likely public domain" ? (
              <p style={{ margin: "4px 0 0" }}>
                Rights status could not be confirmed with high confidence. Verify
                before reproducing or redistributing this document.
              </p>
            ) : null}
          </div>
        </div>

        <div className="viewerSidebarCard">
          <p className="eyebrow">Reading tools</p>
          <div className="viewerSidebarNotes">
            <p>Use left and right arrow keys to move page by page.</p>
            <p>Switch between original, Korean, or parallel reading without leaving the current page.</p>
            <p>Open the scan in a separate tab when you need full-resolution inspection.</p>
          </div>
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
            {!sourcePdfUrl && !digitalizedPdfUrl && !koreanPdfUrl ? (
              <p style={{ color: "var(--muted)", fontSize: "0.88rem", margin: 0 }}>
                No downloadable files are published for this document.
              </p>
            ) : null}
          </div>
        </div>

        <div className="viewerSidebarCard">
          <div className="viewerPageRailHeader">
            <div>
              <p className="eyebrow">Pages</p>
              <h2>Page rail</h2>
            </div>
            <span className="countBadge">{pageCount} pages</span>
          </div>
          <div className="pageIndexList">
            {pages.map((page, index) => (
              <button
                className={index === pageIndex ? "pageIndexButton isActive" : "pageIndexButton"}
                key={page.page_number}
                onClick={() => setPageIndex(index)}
                type="button"
              >
                <span className="pageIndexButtonTop">
                  <strong>Page {page.page_number}</strong>
                  <small>{pageAvailabilityLabel(page)}</small>
                </span>
                <span className="pageIndexSnippet">{summarizePageText(page)}</span>
              </button>
            ))}
          </div>
        </div>
      </aside>

      <section className="viewerMain">
        <div className="viewerToolbar">
          <div className="viewerToolbarGroup">
            <div className="tabGroup">
              <button
                className={readingMode === "digitalized" ? "tabButton isActive" : "tabButton"}
                onClick={() => setReadingMode("digitalized")}
                type="button"
              >
                Original text
              </button>
              <button
                className={readingMode === "korean" ? "tabButton isActive" : "tabButton"}
                onClick={() => setReadingMode("korean")}
                type="button"
              >
                Korean translation
              </button>
              <button
                className={readingMode === "parallel" ? "tabButton isActive" : "tabButton"}
                onClick={() => setReadingMode("parallel")}
                type="button"
              >
                Parallel reading
              </button>
            </div>
            <div className="viewerStatusRow">
              <span className="viewerStatusPill">
                {currentPageNumber ? `Page ${currentPageNumber}` : "No pages"}
              </span>
              <span className="viewerStatusPill">
                {currentOrdinal} of {pageCount}
              </span>
              <span className="viewerStatusPill">{rightsLabel}</span>
            </div>
          </div>

          <div className="viewerPageControls">
            <button
              className="tabButton"
              disabled={pageIndex <= 0}
              onClick={() => setPageIndex((index) => Math.max(index - 1, 0))}
              type="button"
            >
              Previous
            </button>
            {pageCount > 0 ? (
              <label className="viewerPageJump">
                <span>Jump to</span>
                <select
                  onChange={(event) => setPageIndex(Number(event.target.value))}
                  value={pageIndex}
                >
                  {pages.map((page, index) => (
                    <option key={page.page_number} value={index}>
                      Page {page.page_number}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <button
              className="tabButton"
              disabled={pageIndex >= pages.length - 1}
              onClick={() =>
                setPageIndex((index) => Math.min(index + 1, pages.length - 1))
              }
              type="button"
            >
              Next
            </button>
          </div>
        </div>

        <div className="viewerPanels">
          <div
            className={imageZoom === "detail" ? "viewerImagePanel isDetail" : "viewerImagePanel"}
            ref={imagePanelRef}
          >
            <div className="viewerPanelHeader">
              <div>
                <p className="eyebrow">Source image</p>
                <h2>{currentPageNumber ? `Scan page ${currentPageNumber}` : "No page selected"}</h2>
              </div>
              <div className="viewerInlineActions">
                <button
                  className="tabButton"
                  onClick={() =>
                    setImageZoom((mode) => (mode === "fit" ? "detail" : "fit"))
                  }
                  type="button"
                >
                  {imageZoom === "fit" ? "Detail zoom" : "Fit to panel"}
                </button>
                {currentPage?.imageUrl ? (
                  <a
                    className="secondaryLink viewerUtilityLink"
                    href={currentPage.imageUrl}
                    rel="noreferrer"
                    target="_blank"
                  >
                    Open image
                  </a>
                ) : null}
              </div>
            </div>
            <div className="viewerImageStage">
              {currentPage?.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  alt={`Source page ${currentPage.page_number}`}
                  src={currentPage.imageUrl}
                />
              ) : (
                <div className="placeholderCard">No page image available.</div>
              )}
            </div>
          </div>

          <div className="viewerTextPanel" ref={textPanelRef}>
            <div className="viewerPanelHeader">
              <div>
                <p className="eyebrow">Reading view</p>
                <h2>
                  {readingMode === "parallel"
                    ? "Original and Korean side by side"
                    : readingMode === "digitalized"
                      ? "Original transcription"
                      : "Korean translation"}
                </h2>
              </div>
              <div className="viewerInlineMeta">
                <span>{pageAvailabilityLabel(currentPage)}</span>
              </div>
            </div>

            {readingMode === "parallel" ? (
              <div className="viewerTextCompareGrid">
                <TextPanel
                  body={currentTexts.digitalized}
                  eyebrow="Original"
                  title="Digitalized transcription"
                />
                <TextPanel
                  body={currentTexts.korean}
                  eyebrow="Translation"
                  title="Korean translation"
                />
              </div>
            ) : (
              <TextPanel
                body={
                  readingMode === "digitalized"
                    ? currentTexts.digitalized
                    : currentTexts.korean
                }
                eyebrow={readingMode === "digitalized" ? "Original" : "Translation"}
                title={
                  readingMode === "digitalized"
                    ? "Digitalized transcription"
                    : "Korean translation"
                }
              />
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

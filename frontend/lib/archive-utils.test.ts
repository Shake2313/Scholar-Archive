import { describe, expect, it } from "vitest";

import {
  applyDocumentFilters,
  buildEraSections,
  filterDocuments,
  getArchiveOverview,
  getRightsLabel,
  getTopAuthors,
  sortDocuments,
} from "@/lib/archive-utils";
import type { ArchiveDocument } from "@/lib/types";

function makeDoc(overrides: Partial<ArchiveDocument> & { id: number; slug: string; title: string }): ArchiveDocument {
  return {
    author_display: null,
    century_label: null,
    cover_image_path: null,
    digitalized_pdf_path: null,
    doi: null,
    issue: null,
    journal_or_book: null,
    korean_pdf_path: null,
    language: null,
    page_count: 1,
    page_range: null,
    publication_year: null,
    published_at: null,
    requested_page_count: 1,
    rights_assessment: null,
    source_pdf_path: null,
    status: "published",
    storage_bucket: "archive",
    summary: null,
    volume: null,
    ...overrides,
  };
}

const FIXTURE: ArchiveDocument[] = [
  makeDoc({
    id: 1,
    slug: "newton-1704",
    title: "Opticks",
    author_display: "Isaac Newton",
    publication_year: 1704,
    century_label: "18th century",
    language: "English",
    rights_assessment: "likely_public_domain",
    page_count: 240,
    published_at: "2026-03-01T00:00:00Z",
  }),
  makeDoc({
    id: 2,
    slug: "galileo-1610",
    title: "Sidereus Nuncius",
    author_display: "Galileo Galilei",
    publication_year: 1610,
    century_label: "17th century",
    language: "Latin",
    rights_assessment: null,
    page_count: 64,
    published_at: "2026-02-01T00:00:00Z",
  }),
  makeDoc({
    id: 3,
    slug: "zeeman-1918",
    title: "On the Zeeman Effect",
    author_display: "Pieter Zeeman",
    publication_year: 1918,
    century_label: "20th century",
    language: "English",
    rights_assessment: "likely_public_domain_high_confidence",
    page_count: 18,
    published_at: "2026-04-01T00:00:00Z",
  }),
];

describe("getRightsLabel", () => {
  it("returns public domain label for likely_public_domain variants", () => {
    expect(getRightsLabel("likely_public_domain")).toBe("Likely public domain");
    expect(getRightsLabel("likely_public_domain_high_confidence")).toBe("Likely public domain");
  });

  it("returns uncertain label for unknown or manual_review values", () => {
    expect(getRightsLabel(null)).toBe("Rights uncertain");
    expect(getRightsLabel(undefined)).toBe("Rights uncertain");
    expect(getRightsLabel("manual_review_required")).toBe("Rights uncertain");
    expect(getRightsLabel("undetermined")).toBe("Rights uncertain");
  });
});

describe("getArchiveOverview", () => {
  it("computes counts and year range from document list", () => {
    const overview = getArchiveOverview(FIXTURE);
    expect(overview.documentCount).toBe(3);
    expect(overview.authorCount).toBe(3);
    expect(overview.centuryCount).toBe(3);
    expect(overview.languageCount).toBe(2);
    expect(overview.publicDomainCount).toBe(2);
    expect(overview.undeterminedRightsCount).toBe(1);
    expect(overview.earliestYear).toBe(1610);
    expect(overview.latestYear).toBe(1918);
  });

  it("handles empty document list safely", () => {
    const overview = getArchiveOverview([]);
    expect(overview.documentCount).toBe(0);
    expect(overview.earliestYear).toBeNull();
    expect(overview.latestYear).toBeNull();
  });
});

describe("filterDocuments", () => {
  it("matches documents by multi-token query across all text fields", () => {
    const results = filterDocuments(FIXTURE, "newton english");
    expect(results.map((d) => d.slug)).toEqual(["newton-1704"]);
  });

  it("returns all documents when query is empty", () => {
    expect(filterDocuments(FIXTURE, "")).toHaveLength(3);
    expect(filterDocuments(FIXTURE, "  ")).toHaveLength(3);
  });
});

describe("applyDocumentFilters", () => {
  it("filters by year range", () => {
    const results = applyDocumentFilters(FIXTURE, { yearFrom: "1700", yearTo: "1900" });
    expect(results.map((d) => d.slug)).toEqual(["newton-1704"]);
  });

  it("filters by rights bucket", () => {
    const results = applyDocumentFilters(FIXTURE, { rights: "undetermined" });
    expect(results.map((d) => d.slug)).toEqual(["galileo-1610"]);
  });

  it("filters by language case-insensitively", () => {
    const results = applyDocumentFilters(FIXTURE, { language: "LATIN" });
    expect(results.map((d) => d.slug)).toEqual(["galileo-1610"]);
  });
});

describe("sortDocuments", () => {
  it("sorts by title alphabetically", () => {
    const sorted = sortDocuments(FIXTURE, "title");
    expect(sorted.map((d) => d.slug)).toEqual(["zeeman-1918", "newton-1704", "galileo-1610"]);
  });

  it("sorts by oldest first", () => {
    const sorted = sortDocuments(FIXTURE, "oldest");
    expect(sorted.map((d) => d.slug)).toEqual(["galileo-1610", "newton-1704", "zeeman-1918"]);
  });

  it("sorts by pages descending", () => {
    const sorted = sortDocuments(FIXTURE, "pages_desc");
    expect(sorted.map((d) => d.slug)).toEqual(["newton-1704", "galileo-1610", "zeeman-1918"]);
  });

  it("sorts by recent first using published_at", () => {
    const sorted = sortDocuments(FIXTURE, "recent");
    expect(sorted.map((d) => d.slug)).toEqual(["zeeman-1918", "newton-1704", "galileo-1610"]);
  });
});

describe("getTopAuthors", () => {
  it("returns authors sorted by document count", () => {
    const extra = makeDoc({
      id: 4,
      slug: "newton-1687",
      title: "Principia",
      author_display: "Isaac Newton",
      publication_year: 1687,
    });
    const top = getTopAuthors([...FIXTURE, extra], 3);
    expect(top[0].label).toBe("Isaac Newton");
    expect(top[0].count).toBe(2);
  });
});

describe("buildEraSections", () => {
  it("groups documents by century and sorts oldest first", () => {
    const sections = buildEraSections(FIXTURE, "oldest");
    const labels = sections.map((s) => s.label);
    expect(labels).toEqual(["17th century", "18th century", "20th century"]);
  });

  it("each section has correct document count", () => {
    const sections = buildEraSections(FIXTURE, "oldest");
    expect(sections.find((s) => s.label === "18th century")?.documentCount).toBe(1);
  });
});

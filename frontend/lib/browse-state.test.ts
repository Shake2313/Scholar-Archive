import { describe, expect, it } from "vitest";

import {
  buildBrowseCatalogState,
  buildBrowseFilterValues,
} from "@/lib/browse-state";
import type { ArchiveDocument } from "@/lib/types";

const documents: ArchiveDocument[] = [
  {
    id: 1,
    slug: "zeeman-1918",
    title: "On the Zeeman Effect",
    author_display: "Pieter Zeeman",
    publication_year: 1918,
    century_label: "20th century",
    language: "English",
    journal_or_book: "Physical Review",
    volume: "12",
    issue: "3",
    page_range: "101-118",
    doi: "10.1000/zeeman",
    summary: null,
    storage_bucket: "archive",
    source_pdf_path: "source.pdf",
    digitalized_pdf_path: "digitalized.pdf",
    korean_pdf_path: "korean.pdf",
    cover_image_path: null,
    page_count: 18,
    requested_page_count: 18,
    rights_assessment: "likely_public_domain",
    published_at: "2026-04-02T00:00:00Z",
    status: "published",
  },
  {
    id: 2,
    slug: "galileo-1610",
    title: "Sidereus Nuncius",
    author_display: "Galileo Galilei",
    publication_year: 1610,
    century_label: "17th century",
    language: "Latin",
    journal_or_book: "Venice Press",
    volume: null,
    issue: null,
    page_range: "1-64",
    doi: null,
    summary: null,
    storage_bucket: "archive",
    source_pdf_path: null,
    digitalized_pdf_path: "galileo-digitalized.pdf",
    korean_pdf_path: null,
    cover_image_path: null,
    page_count: 64,
    requested_page_count: 64,
    rights_assessment: "manual_review_required",
    published_at: "2026-03-30T00:00:00Z",
    status: "published",
  },
  {
    id: 3,
    slug: "newton-1704",
    title: "Opticks",
    author_display: "Isaac Newton",
    publication_year: 1704,
    century_label: "18th century",
    language: "English",
    journal_or_book: "Royal Society",
    volume: "1",
    issue: "1",
    page_range: "1-240",
    doi: null,
    summary: null,
    storage_bucket: "archive",
    source_pdf_path: "newton-source.pdf",
    digitalized_pdf_path: "newton-digitalized.pdf",
    korean_pdf_path: "newton-korean.pdf",
    cover_image_path: null,
    page_count: 240,
    requested_page_count: 240,
    rights_assessment: "likely_public_domain",
    published_at: "2026-04-01T00:00:00Z",
    status: "published",
  },
];

describe("browse-state", () => {
  it("normalizes multi-value search params into a stable filter object", () => {
    const values = buildBrowseFilterValues({
      q: ["zeeman", "ignored"],
      author: ["Pieter Zeeman"],
      year_from: ["1900"],
      sort: ["author"],
    });

    expect(values).toMatchObject({
      query: "zeeman",
      author: "Pieter Zeeman",
      yearFrom: "1900",
      sort: "author",
    });
  });

  it("filters and sorts the browse catalog while preserving collection overview data", () => {
    const state = buildBrowseCatalogState(documents, {
      q: "english",
      year_from: "1700",
      rights: "public_domain",
      sort: "pages_desc",
    });

    expect(state.filteredDocuments.map((document) => document.slug)).toEqual([
      "newton-1704",
      "zeeman-1918",
    ]);
    expect(state.languageOptions).toEqual(["English", "Latin"]);
    expect(state.overview).toMatchObject({
      documentCount: 3,
      authorCount: 3,
      publicDomainCount: 2,
      earliestYear: 1610,
      latestYear: 1918,
    });
  });
});

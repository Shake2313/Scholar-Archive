import {
  applyDocumentFilters,
  getArchiveOverview,
  getLanguageOptions,
  normalizeBrowseSort,
  sortDocuments,
  type ArchiveBrowseSort,
  type ArchiveOverview,
} from "@/lib/archive";
import type { ArchiveDocument } from "@/lib/types";

export type BrowseSearchParams = {
  q?: string | string[];
  title?: string | string[];
  author?: string | string[];
  journal?: string | string[];
  volume?: string | string[];
  issue?: string | string[];
  year_from?: string | string[];
  year_to?: string | string[];
  language?: string | string[];
  rights?: string | string[];
  sort?: string | string[];
};

export type BrowseFilterValues = {
  query: string;
  title: string;
  author: string;
  journal: string;
  volume: string;
  issue: string;
  yearFrom: string;
  yearTo: string;
  language: string;
  rights: string;
  sort: ArchiveBrowseSort;
};

export type BrowseCatalogState = {
  values: BrowseFilterValues;
  filteredDocuments: ArchiveDocument[];
  languageOptions: string[];
  overview: ArchiveOverview;
};

export function readSearchParam(
  value: string | string[] | undefined,
): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export function buildBrowseFilterValues(
  params: BrowseSearchParams = {},
): BrowseFilterValues {
  return {
    query: readSearchParam(params.q),
    title: readSearchParam(params.title),
    author: readSearchParam(params.author),
    journal: readSearchParam(params.journal),
    volume: readSearchParam(params.volume),
    issue: readSearchParam(params.issue),
    yearFrom: readSearchParam(params.year_from),
    yearTo: readSearchParam(params.year_to),
    language: readSearchParam(params.language),
    rights: readSearchParam(params.rights),
    sort: normalizeBrowseSort(readSearchParam(params.sort)),
  };
}

export function buildBrowseCatalogState(
  documents: ArchiveDocument[],
  params: BrowseSearchParams = {},
): BrowseCatalogState {
  const values = buildBrowseFilterValues(params);

  return {
    values,
    filteredDocuments: sortDocuments(
      applyDocumentFilters(documents, values),
      values.sort,
    ),
    languageOptions: getLanguageOptions(documents),
    overview: getArchiveOverview(documents),
  };
}

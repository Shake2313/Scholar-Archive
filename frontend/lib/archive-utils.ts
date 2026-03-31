import type { ArchiveDocument } from "@/lib/types";

export type ArchiveBrowseSort = "recent" | "oldest" | "title";

export type ArchiveFilterOptions = {
  query?: string;
  language?: string;
  rights?: string;
};

export type ArchiveOverview = {
  documentCount: number;
  authorCount: number;
  centuryCount: number;
  languageCount: number;
  publicDomainCount: number;
  undeterminedRightsCount: number;
  earliestYear: number | null;
  latestYear: number | null;
};

export type ArchiveFacet = {
  label: string;
  count: number;
};

export type ArchiveYearBucket = {
  label: string;
  year: number | null;
  count: number;
  documents: ArchiveDocument[];
};

export type ArchiveEraSection = {
  id: string;
  label: string;
  documentCount: number;
  yearRangeLabel: string;
  yearBuckets: ArchiveYearBucket[];
};

function normalizeText(value: string | null | undefined): string {
  return String(value ?? "").trim().toLowerCase();
}

function normalizeRightsBucket(
  assessment: string | null | undefined,
): "public_domain" | "undetermined" {
  return assessment?.startsWith("likely_public_domain")
    ? "public_domain"
    : "undetermined";
}

export function getRightsLabel(assessment: string | null | undefined): string {
  return normalizeRightsBucket(assessment) === "public_domain"
    ? "Likely public domain"
    : "Rights uncertain";
}

export function normalizeBrowseSort(
  value: string | null | undefined,
): ArchiveBrowseSort {
  if (value === "oldest" || value === "title") {
    return value;
  }
  return "recent";
}

export function filterDocuments(
  documents: ArchiveDocument[],
  query: string,
): ArchiveDocument[] {
  const q = query.trim().toLowerCase();
  if (!q) {
    return documents;
  }
  return documents.filter((document) =>
    [
      document.title,
      document.author_display,
      document.journal_or_book,
      document.century_label,
      document.language,
      document.publication_year,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(q)),
  );
}

export function applyDocumentFilters(
  documents: ArchiveDocument[],
  options: ArchiveFilterOptions,
): ArchiveDocument[] {
  const query = options.query?.trim() ?? "";
  const language = normalizeText(options.language);
  const rights = normalizeText(options.rights);
  return filterDocuments(documents, query).filter((document) => {
    if (language && normalizeText(document.language) !== language) {
      return false;
    }
    if (rights && normalizeRightsBucket(document.rights_assessment) !== rights) {
      return false;
    }
    return true;
  });
}

export function sortDocuments(
  documents: ArchiveDocument[],
  sort: ArchiveBrowseSort,
): ArchiveDocument[] {
  return [...documents].sort((left, right) => {
    if (sort === "title") {
      return left.title.localeCompare(right.title);
    }
    if (sort === "oldest") {
      const leftYear = left.publication_year ?? Number.MAX_SAFE_INTEGER;
      const rightYear = right.publication_year ?? Number.MAX_SAFE_INTEGER;
      return leftYear - rightYear || left.title.localeCompare(right.title);
    }
    const leftTime = left.published_at ? Date.parse(left.published_at) : 0;
    const rightTime = right.published_at ? Date.parse(right.published_at) : 0;
    return rightTime - leftTime || left.title.localeCompare(right.title);
  });
}

export function getArchiveOverview(
  documents: ArchiveDocument[],
): ArchiveOverview {
  const years = documents
    .map((document) => document.publication_year)
    .filter((value): value is number => typeof value === "number");
  const authors = new Set(
    documents
      .map((document) => document.author_display?.trim())
      .filter((value): value is string => Boolean(value)),
  );
  const centuries = new Set(
    documents
      .map((document) => document.century_label?.trim())
      .filter((value): value is string => Boolean(value)),
  );
  const languages = new Set(
    documents
      .map((document) => document.language?.trim())
      .filter((value): value is string => Boolean(value)),
  );
  const publicDomainCount = documents.filter(
    (document) => normalizeRightsBucket(document.rights_assessment) === "public_domain",
  ).length;
  return {
    documentCount: documents.length,
    authorCount: authors.size,
    centuryCount: centuries.size,
    languageCount: languages.size,
    publicDomainCount,
    undeterminedRightsCount: Math.max(documents.length - publicDomainCount, 0),
    earliestYear: years.length ? Math.min(...years) : null,
    latestYear: years.length ? Math.max(...years) : null,
  };
}

export function getLanguageOptions(documents: ArchiveDocument[]): string[] {
  return Array.from(
    new Set(
      documents
        .map((document) => document.language?.trim())
        .filter((value): value is string => Boolean(value)),
    ),
  ).sort((left, right) => left.localeCompare(right));
}

function formatCenturyLabel(century: number): string {
  const suffix =
    century % 100 >= 11 && century % 100 <= 13
      ? "th"
      : ({ 1: "st", 2: "nd", 3: "rd" }[century % 10] ?? "th");
  return `${century}${suffix} century`;
}

function getCenturyNumber(document: ArchiveDocument): number | null {
  if (typeof document.publication_year === "number" && document.publication_year > 0) {
    return Math.floor((document.publication_year - 1) / 100) + 1;
  }
  const match = String(document.century_label ?? "").match(/^(\d+)/);
  return match ? Number(match[1]) : null;
}

function getEraSectionId(label: string): string {
  return `era-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "undated"}`;
}

export function buildEraSections(
  documents: ArchiveDocument[],
  sort: ArchiveBrowseSort = "oldest",
): ArchiveEraSection[] {
  const sectionMap = new Map<
    string,
    {
      label: string;
      centuryNumber: number | null;
      years: Map<number, ArchiveDocument[]>;
      undated: ArchiveDocument[];
    }
  >();

  for (const document of documents) {
    const centuryNumber = getCenturyNumber(document);
    const label =
      centuryNumber !== null
        ? formatCenturyLabel(centuryNumber)
        : document.century_label ?? "Undated";
    const existing = sectionMap.get(label) ?? {
      label,
      centuryNumber,
      years: new Map<number, ArchiveDocument[]>(),
      undated: [],
    };
    if (typeof document.publication_year === "number") {
      const yearDocs = existing.years.get(document.publication_year) ?? [];
      yearDocs.push(document);
      existing.years.set(document.publication_year, yearDocs);
    } else {
      existing.undated.push(document);
    }
    sectionMap.set(label, existing);
  }

  const descending = sort === "recent";
  const documentSort: ArchiveBrowseSort = sort === "title" ? "title" : descending ? "recent" : "oldest";

  const sections = Array.from(sectionMap.values()).map((section) => {
    const numericYears = Array.from(section.years.keys()).sort((left, right) =>
      descending ? right - left : left - right,
    );
    const yearBuckets: ArchiveYearBucket[] = numericYears.map((year) => ({
      label: String(year),
      year,
      count: section.years.get(year)?.length ?? 0,
      documents: sortDocuments(section.years.get(year) ?? [], documentSort),
    }));
    if (section.undated.length) {
      yearBuckets.push({
        label: "Undated",
        year: null,
        count: section.undated.length,
        documents: sortDocuments(section.undated, documentSort),
      });
    }

    const yearRangeLabel =
      numericYears.length > 0
        ? `${Math.min(...numericYears)}-${Math.max(...numericYears)}`
        : "Undated";

    return {
      id: getEraSectionId(section.label),
      label: section.label,
      documentCount: yearBuckets.reduce((total, bucket) => total + bucket.count, 0),
      yearRangeLabel,
      yearBuckets,
    };
  });

  return sections.sort((left, right) => {
    const leftCentury = sectionMap.get(left.label)?.centuryNumber ?? null;
    const rightCentury = sectionMap.get(right.label)?.centuryNumber ?? null;
    if (leftCentury === null && rightCentury === null) {
      return left.label.localeCompare(right.label);
    }
    if (leftCentury === null) {
      return 1;
    }
    if (rightCentury === null) {
      return -1;
    }
    return descending ? rightCentury - leftCentury : leftCentury - rightCentury;
  });
}

export function groupDocumentsByCentury(documents: ArchiveDocument[]) {
  return documents.reduce<Record<string, ArchiveDocument[]>>((groups, document) => {
    const key = document.century_label ?? "Undated";
    groups[key] = groups[key] ?? [];
    groups[key].push(document);
    return groups;
  }, {});
}

export function groupDocumentsByAuthor(documents: ArchiveDocument[]) {
  return documents.reduce<Record<string, ArchiveDocument[]>>((groups, document) => {
    const key = document.author_display ?? "Unknown author";
    groups[key] = groups[key] ?? [];
    groups[key].push(document);
    return groups;
  }, {});
}

export function getTopAuthors(
  documents: ArchiveDocument[],
  limit = 6,
): ArchiveFacet[] {
  const groups = groupDocumentsByAuthor(documents);
  return Object.entries(groups)
    .map(([label, items]) => ({ label, count: items.length }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))
    .slice(0, limit);
}

export function getTopCenturies(
  documents: ArchiveDocument[],
  limit = 6,
): ArchiveFacet[] {
  const groups = groupDocumentsByCentury(documents);
  return Object.entries(groups)
    .map(([label, items]) => ({ label, count: items.length }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))
    .slice(0, limit);
}

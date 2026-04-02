import type { ArchiveBrowseSort } from "@/lib/archive";

type CatalogFilterValues = {
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

export function CatalogFilters({
  idPrefix,
  resetHref,
  languageOptions,
  values,
}: {
  idPrefix: string;
  resetHref: string;
  languageOptions: string[];
  values: CatalogFilterValues;
}) {
  return (
    <form className="catalogFilters" method="get">
      <div className="catalogFilterField catalogFilterFieldWide">
        <label htmlFor={`${idPrefix}-query`}>General search</label>
        <input
          defaultValue={values.query}
          id={`${idPrefix}-query`}
          name="q"
          placeholder="Any field: title, author, journal, year, volume, issue, DOI"
        />
      </div>
      <div className="catalogFilterField">
        <label htmlFor={`${idPrefix}-sort`}>Sort</label>
        <select defaultValue={values.sort} id={`${idPrefix}-sort`} name="sort">
          <option value="recent">Most recent</option>
          <option value="oldest">Oldest publication year</option>
          <option value="title">Title A-Z</option>
          <option value="author">Author A-Z</option>
          <option value="pages_desc">Longest documents</option>
        </select>
      </div>
      <div className="catalogFilterField">
        <label htmlFor={`${idPrefix}-language`}>Language</label>
        <select
          defaultValue={values.language}
          id={`${idPrefix}-language`}
          name="language"
        >
          <option value="">All languages</option>
          {languageOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>
      <div className="catalogFilterField">
        <label htmlFor={`${idPrefix}-rights`}>Rights</label>
        <select defaultValue={values.rights} id={`${idPrefix}-rights`} name="rights">
          <option value="">All rights signals</option>
          <option value="public_domain">Likely public domain</option>
          <option value="undetermined">Rights uncertain</option>
        </select>
      </div>

      <div className="catalogFilterField">
        <label htmlFor={`${idPrefix}-title`}>Title</label>
        <input
          defaultValue={values.title}
          id={`${idPrefix}-title`}
          name="title"
          placeholder="Exact title words"
        />
      </div>
      <div className="catalogFilterField">
        <label htmlFor={`${idPrefix}-author`}>Author</label>
        <input
          defaultValue={values.author}
          id={`${idPrefix}-author`}
          name="author"
          placeholder="Author name"
        />
      </div>
      <div className="catalogFilterField">
        <label htmlFor={`${idPrefix}-journal`}>Journal or book</label>
        <input
          defaultValue={values.journal}
          id={`${idPrefix}-journal`}
          name="journal"
          placeholder="Series, journal, collection"
        />
      </div>
      <div className="catalogFilterField">
        <label htmlFor={`${idPrefix}-volume`}>Volume</label>
        <input
          defaultValue={values.volume}
          id={`${idPrefix}-volume`}
          name="volume"
          placeholder="Volume"
        />
      </div>
      <div className="catalogFilterField">
        <label htmlFor={`${idPrefix}-issue`}>Issue</label>
        <input
          defaultValue={values.issue}
          id={`${idPrefix}-issue`}
          name="issue"
          placeholder="Issue"
        />
      </div>
      <div className="catalogFilterField">
        <label htmlFor={`${idPrefix}-year-from`}>Year from</label>
        <input
          defaultValue={values.yearFrom}
          id={`${idPrefix}-year-from`}
          inputMode="numeric"
          name="year_from"
          placeholder="1700"
        />
      </div>
      <div className="catalogFilterField">
        <label htmlFor={`${idPrefix}-year-to`}>Year to</label>
        <input
          defaultValue={values.yearTo}
          id={`${idPrefix}-year-to`}
          inputMode="numeric"
          name="year_to"
          placeholder="1800"
        />
      </div>

      <div className="catalogFilterActions">
        <button type="submit">Apply filters</button>
        <a className="catalogResetLink" href={resetHref}>
          Clear filters
        </a>
      </div>
    </form>
  );
}

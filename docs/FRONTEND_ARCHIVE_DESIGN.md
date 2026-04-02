# Frontend Archive Design Direction

## Product framing

Scholar Archive should feel like a public-facing archive portal, not a startup landing page and not a nostalgic retro government website.

The reference direction is:

- trust and institutional clarity from a national archive or classical literature database
- modern browsing and reading usability
- metadata-first navigation

The visual tone should communicate:

- authority
- stability
- readability
- careful preservation of source materials

## Core principles

### 1. Public archive before product marketing

The home page should act as a search and navigation gateway for a document collection.

It should emphasize:

- what this archive contains
- how to search it
- how to browse by stable scholarly axes such as era, author, and publication metadata

It should avoid:

- oversized marketing copy
- app-like feature selling
- decorative hero sections with weak information value

### 2. Metadata-first navigation

The archive should be navigable through bibliographic structure.

Primary access paths:

- free-text search
- era / publication year / century
- author
- journal or book
- rights status

### 3. Reading-oriented detail pages

Document detail pages should feel like a reading room.

The user should be able to:

- understand the bibliographic record quickly
- move page by page through source images
- compare digitalized text and Korean translation
- download source artifacts without losing context

### 4. Quiet authority

The interface should be calm, legible, and official.

Recommended tone:

- restrained color
- strong spacing and hierarchy
- table/list structures where appropriate
- typography with editorial seriousness

## Visual direction

### Color

Base palette:

- paper ivory backgrounds
- dark navy or ink for headings and navigation
- muted bronze or brick for accents
- soft gray-brown borders

Avoid:

- bright startup colors
- heavy gradients
- playful saturation

### Typography

Use a split system:

- headings: serif with formal editorial character
- body and UI controls: highly legible text face

The target feeling is "catalog + reading room", not "luxury magazine".

### Components

Prefer:

- list and table hybrids
- metadata badges with restrained styling
- record panels
- filter rails
- sectional dividers

Use cards sparingly and only when they help scanning.

## Information architecture

### Home

Purpose:

- act as the archive gateway
- direct users into search and stable browse paths

Structure:

1. Search portal
2. Quick entry points for catalog, era, author
3. Collection overview metrics
4. Featured browse clusters, not just featured documents
5. Recent additions

### Catalog (`/browse`)

Purpose:

- be the default archive browsing surface

Structure:

1. Search bar
2. Left filter rail or persistent filter block
3. Results summary row
4. Result list with strong metadata

Each result should show:

- title
- author
- publication year
- century
- journal/book
- language
- rights signal

### Browse by era

Purpose:

- support exploratory movement through time

Should emphasize:

- year buckets
- century labels
- counts per era

### Browse by author

Purpose:

- support author-centric discovery

Should emphasize:

- normalized author grouping
- document counts
- quick jump by author cluster

### Document detail

Purpose:

- support real reading and archival reference

Structure:

1. bibliographic record header
2. tabs for source image / digitalized text / Korean translation / record info / downloads
3. page navigation with clear position context
4. stable rights and source metadata panel

## UX rules

### Home page

- search must be visually dominant
- recent documents should not be the only hero content
- era and author entry points must be visible above the fold on desktop

### List pages

- filters should stay visible while scanning results
- result count and active filters should be obvious
- empty states should explain what to relax

### Detail page

- the reading surface should have more space than the metadata surface
- metadata should be easy to inspect without competing with the text
- page movement should be possible without scrolling back to the top

## Implementation sequence

### Phase 1: foundation

- home as archive gateway
- unified catalog route
- shared filter and sort utilities

### Phase 2: archive browsing depth

- stronger era and year organization
- richer result metadata presentation
- more robust list-page filtering and sorting

### Phase 3: reading experience

- better page navigation
- stronger source image and text reading layout
- clearer downloads and citation metadata

### Phase 4: search and polish

- field-aware search
- refined empty states and microcopy
- mobile reading behavior tuning

## Checklist mapping

- home gateway and entry flow: in progress foundation completed
- era/year organization: next
- list-page metadata/filter improvements: next
- detail reading UX: next
- stronger search: after browsing structure is stable

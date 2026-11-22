# Data Notes — The Metropolitan Museum of Art

## Data source

- **Dataset:** The Met Open Access collection metadata
- **Source:** https://github.com/metmuseum/openaccess
- **Original file:** `MetObjects.csv`
- **Additional source:** The Met Collection API — https://metmuseum.github.io/

The original CSV is preserved unchanged. Our application uses a cleaned subset.

## Relevant fields

We identified the following groups of metadata:

- **Identification:** `Object ID`, `Object Number`, `Title`, `Object Name`
- **Classification:** `Department`, `Classification`
- **Artist:** `Artist Display Name`, `Artist Role`, `Artist Display Bio`, `Artist Nationality`, artist dates
- **Dating:** `Object Date`, `Object Begin Date`, `Object End Date`, `Period`, `Dynasty`, `Reign`
- **Description:** `Medium`, `Dimensions`, `Culture`
- **Geography:** `Country`, `Region`, `City`, `Geography Type`
- **Discovery:** `Tags`
- **Links:** `Link Resource`, object and artist Wikidata URLs
- **Rights:** `Is Public Domain`, `Rights and Reproduction`, `Credit Line`

## Data observations

- The collection contains many object types, not only paintings and sculptures.
- `Object Name` values are highly varied and sometimes inconsistent in capitalization or wording.
- `Classification`, `Object Name`, and `Department` can help assign broader categories.
- `Tags` contains multiple values separated by `|`, such as `Landscapes|Mountains|Fog`.
- Artist, date, geographic, and descriptive information may be missing or incomplete.
- Some objects have unknown artists; these should not automatically be excluded.
- The CSV does not provide image URLs or reliably establish image availability.

## Inclusion and cleaning decisions

- Include only records where `Is Public Domain` is explicitly `True`.
- Keep valid objects from selected art categories.
- Normalize categories using `Classification`, `Object Name`, and selected department fallbacks.
- Deduplicate by `Object ID`.
- Keep missing optional metadata as `null`.
- Split `Tags` into arrays.
- Preserve original classification and object-name values.
- Export categorized records as JSONL for later PostgreSQL ingestion.

## Image handling

Image URLs will be retrieved separately through The Met Collection API.

Relevant API fields include `primaryImage`, `primaryImageSmall`, and `additionalImages`.

A public-domain flag does not guarantee an available image. Image availability must be checked separately.

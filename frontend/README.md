# Air Quality dashboard

React, TypeScript, Vite, Tailwind CSS 4, and React Leaflet.

Quick setup in Vietnamese: [Thiết lập web dashboard](../docs/setup-web-dashboard.md).

## Development

Start the [FastAPI backend](../backend/README.md) on port 8000 first, then run
these commands from `frontend/` in a second terminal:

```sh
npm ci
npm run dev
```

```sh
npm run lint
npm run build
npm run preview
```

`/user` loads its data from `GET /api/dashboard`. `/admin`
loads its management view from `GET /api/admin/dashboard` through the same Vite
API proxy.
In-flight requests are shared across React StrictMode mounts. Completed windows
are cached for 15 seconds, limited to eight windows and 60,000 records, and
cleared when a new generation is observed. Requests are cancelled when their
last subscriber leaves; switching views cannot replace a newer result with a
late response. Retrying bypasses completed caches. Time filters
fetch a new bounded period; province, metric and sector selections are local.
The default view shows each 3-hour UTC observation over the last seven source
days. Date/time controls use UTC, with a maximum native window of 31 days.
Daily/monthly resolution supports longer exploration. Comparisons fetch the
same date/time window in the chosen year; Admin YoY uses the previous year,
keeping comparison records separate from the primary series. February 29 maps
to February 28 when necessary. CSV includes full UTC timestamps.
Admin primary data renders as soon as it arrives; only the YoY card waits for
its reference period. Comparison failures leave current readings available and
show a separate retry message. Explicit comparisons request only their selected
reference window, without fetching another previous year.
The map labels its latest valid timestamp inside the queried period. The dashboard
layout and local GeoJSON map render independently of that request. While it is
pending, KPI cards, charts, comparison and emissions show animated skeletons
(respecting reduced-motion preferences). A failed request leaves static
placeholders and an inline error with a retry button; it never replaces the
whole dashboard. Requests time out after 30 seconds; daily aggregation requests
allow 120 seconds because a full year scans native observations before aggregating.

Province/sector selectors and exports remain unavailable until their data is
ready. Map exploration and other filters stay usable. Retrying preserves the
map instance, zoom, local highlight and filter choices; recovered readings
update the existing map layers. Successful empty responses use the normal
empty-data UI, not error/loading placeholders. There is no local mock fallback.
Retrying fetches fresh data; recent completed windows can be reused until their
short cache expires. Native sample availability is 2024–2025; older history is
available as monthly aggregates.
Local full ETL generations can expose native years back to 2003; the year
selector follows the observations present on disk. Both pages include a
paginated observation table with one region/timestamp per row and CSV export
of all filtered rows, retaining missing values and full UTC timestamps.
Observation panels are capped at 960px, with fixed column proportions, alternating
row colors, sticky headings and internal scrolling on narrow screens. Other
management tables share the same alternating row colors and retain their selected
province highlight.

Vite dev and preview proxy `/api` to `http://127.0.0.1:8000`. To override it,
copy `.env.example` to `.env.local`, change `API_PROXY_TARGET`, and restart Vite.
Production output is `dist/app/`. Deploy
that directory and configure your web server to reverse-proxy `/api/*` to
FastAPI, preserving the prefix.

## Structure

- `src/main.tsx`: React entry point and global stylesheet import.
- `src/App.tsx`: application-level route selection for `/user` and `/admin`.
- `src/pages/user/UserDashboard.tsx`: map-first monitoring, current AQI, compact pollutants and one trend.
- `src/pages/admin/AdminDashboard.tsx`: five KPIs, smaller map with adjacent trend/ranking, and analytics tabs.
- `src/pages/admin/AdminAnalytics.tsx`: overview/comparison, pollutants, provinces, emissions, QCVN and data quality panels.
- `src/features/dashboard/model/`: period/province/metric selectors, validation, observation insights and Admin calculations.
- `src/features/dashboard/api/`: user/Admin endpoints and bounded, cancellable request caching.
- `src/features/dashboard/hooks/`: primary/comparison request lifecycle, loading, errors and retry.
- `src/features/dashboard/types.ts`: dashboard data and filter contracts.
- `src/features/dashboard/components/`: filters, calendar, KPIs, comparisons and observation/management tables.
- `src/components/ui/`: shared buttons, form controls, icons, loading/error states and exports.
- `src/features/analytics/`: responsive SVG charts and single-observation summaries.
- `src/features/geography/`: map layers and province-data loading.
- `../backend/data/samples/`: current temporary CAMS sample, served by the API; not validated Gold data.
- `public/data/`: prepared map GeoJSON served as static assets.
- `public/favicon.svg`: application icon.

Feature code stays beside its components, model, API and hooks; only shared
UI and date/number formatting live outside features. Empty scaffold directories
and the retired backend demo source have been removed. The Vite, TypeScript,
ESLint and npm lock files support development and reproducible builds.

## Styling

Use Tailwind utility classes in React components. The Vite integration follows the [official Tailwind setup](https://tailwindcss.com/docs/installation/using-vite).

- `src/index.css` is the stylesheet entry for Tailwind, theme tokens and Leaflet. Dashboard cards use Tailwind utilities; compact filters, calendars and responsive popovers use shared component classes in the same stylesheet.
- Theme tokens use `@theme`, for example `bg-surface`, `text-accent`, `border-border`, `rounded-card`, and `shadow-card`.
- The dashboard uses a single light theme with a pale mint page, white cards, dark green text and teal controls/charts. Active controls, the AQI summary and important KPIs use teal, AQI-colored or amber highlights. The light blue map has neutral land and a dark blue selected-province outline. Missing/unclassified readings remain neutral. AQI map colors run from green to deep red; companion text colors preserve readability on light cards and tooltips.
- `src/components/ui/Button.tsx` provides buttons and segmented controls. `FormControls.tsx` provides labeled fields, selects, and date inputs. These include focus, disabled, and reduced-motion states.
- Keep conditional utility names complete so Tailwind can detect them at build time. Use `aria-pressed` for segmented control selection.
- Leaflet's vendor stylesheet is imported into the `components` layer so Tailwind utilities can override it. Map controls and tooltips use Tailwind descendant variants. Leaflet still handles geographic geometry, positioning, and dynamic path styles; those styles reference the same `--color-*` theme tokens.
- Charts use the shared theme tokens. SVG export resolves computed colors, strokes, gradients and typography so downloads work independently of the dashboard stylesheet.

## Province map boundaries

The map reads `public/data/vietnam-provinces.geojson`, a standalone frontend asset containing all 34 province boundaries from `../data/landing/reference/vietnamese-provinces-database/json/geojson/` (dataset `v5.1.0`). Every source coordinate and MultiPolygon ring is preserved, including islands and holes. Only province identifiers, names, area, and geometry are bundled; ward data is not needed.

The GeoJSON is committed and served directly by Vite. Building or deploying `frontend` alone does not require the reference directory or a data-generation script.

Clicking a province draws its geometry in a separate, non-interactive highlight layer above the map. Provinces without air-quality readings can also be highlighted; only provinces with readings update the dashboard filters. Changing a province filter resets the map selection. Keyboard focus follows the province outline, and Enter/Space selects it.

## World basemap

`WorldBasemap.tsx` draws pale neutral land on a light blue sea, using a non-interactive vector background from `public/data/world-countries.geojson`. It contains country outlines only: no roads, place labels, satellite images, or provincial boundaries outside Vietnam. Vietnam is excluded from the background and drawn exclusively from the existing detailed province asset above it.

The background source is [Natural Earth Admin 0 at 1:110m](https://www.naturalearthdata.com/downloads/110m-cultural-vectors/110m-admin-0-countries/), pinned to the `v5.1.2` repository release. Natural Earth data is [public domain](https://www.naturalearthdata.com/about/terms-of-use/). Its coarse Vietnam outline differs from the province dataset, so using it directly would leave gaps and overlaps along the land border.

The committed world asset already contains the corrected border arcs of China, Laos, and Cambodia, using matching coordinates from the union of Vietnam's province geometries. Shared three-country junctions use identical connectors. The province geometry remains at its original resolution, while the rest of the background stays coarse. Leaflet uses `smoothFactor: 0` on both layers so it does not simplify their shared coordinates differently when zooming.

The frontend consumes these prepared GeoJSON files directly; there is no generation step or Python/GIS dependency. When replacing map data in the future, update the two assets together and verify that the shared borders still match.

The generated asset has 176 country features and 23,839 positions, about 504 KiB uncompressed (172 KiB gzipped). The background is fetched once from the app's own origin and cached in memory. Its geometry stays mounted across province filters and metric changes. Panning and zooming make no additional background requests. Loading runs independently of province data; a failed background request leaves the province layer and dashboard controls available. The background pane sits below province boundaries and does not receive pointer events.

Local Chromium validation covered one background request across filter changes, pan and zoom; absence of image tiles and external map requests; country outlines; province keyboard selection; widths down to 320px; and slow/failed background loading. With 4x CPU throttling, three runs before and after border alignment measured a pan/zoom frame interval at the 95th percentile of about 17 ms. Province rendering was ready in approximately 0.60–0.62 s before and after alignment; the maximum observed frame interval increased from 50 ms to 67 ms. These are local measurements, not a guarantee for every device.

## Dashboard behavior

Both routes share a compact filter toolbar: one row on wide screens and two
rows on phones. The toolbar sticks near the top while scrolling. On phones it
collapses to a 54px summary of the region, metric and period; tapping **Bộ lọc**
expands the controls in place, and **Thu gọn** restores the summary. Scroll
padding follows the toolbar height to keep focused/anchored content visible.
Province and metric controls support search,
Vietnamese names without accents, arrow keys and Enter. Province selection,
pollutant and period feed the same selectors for metrics, charts, map values and tables.
The calendar opens as a centered dialog on every screen, at most 480px wide
and 620px tall, constrained to the viewport. Its header and action footer stay
visible while the body scrolls; the visible viewport is used when a phone
keyboard reduces the available space. A single month keeps the layout compact;
month arrows/selectors support ranges across months. The selected UTC hour
appears beside the date on desktop and in each date card's heading on phones;
tapping that hour opens the eight explicit 3-hour choices. Start and end dates
have separate numbered cards, distinct backgrounds and a connecting arrow.
Focusing a date card selects which endpoint the calendar edits, with a visible
instruction. Quick choices expand on demand and collapse after selection;
their Vietnamese labels use “7 ngày gần nhất”, “30 ngày gần nhất” and similar
phrasing, explicitly relative to the latest source date. It supports these presets,
month/year navigation and full-year selection at daily/monthly resolution.
Changes inside the calendar remain a draft until **Áp dụng**; **Hủy**, outside
click or Escape discard the draft and restore focus. Invalid bounds, unavailable
dates and excessive ranges are explained before any API request. On phones,
time resolution is selected inside the calendar. Adjacent-period arrows on the
toolbar stop at source boundaries; on phones these controls are inside the
calendar. The reset button restores source defaults.
Visible copy, source/aggregation labels, emission sectors, request errors,
document title, and map zoom controls use Vietnamese. Scientific symbols,
source names and standard UTC/CSV/SVG abbreviations retain their identifiers;
filter keys and API contracts remain unchanged.
Day labels and manual inputs consistently use `dd/mm/yyyy`; UTC times use
`HH:mm` (including seconds in the observation table). Monthly aggregates retain
their `mm/yyyy` period label. API parameters, chronological keys and CSV exports
retain ISO timestamps. Native controls also offer **Một thời điểm**, which submits
the same UTC instant for both bounds and requires only one date and hour.

With a single valid time point, the trend panel becomes an observation summary:
a large value and unit, an explicit timestamp, regional coverage/rank, bars for
the highest regions and the selected region, and a numerical comparison.
Regional context is recomputed at that exact point/represented calendar period,
including when other regions have additional points in the requested range.
Missing values are excluded, zero and negative values are retained, and ties
share ranks. A single point does not imply a temporal increase or decrease.
The expand action requests a real seven-day or twelve-month window inside the
source's bounds and returns to the line chart. SVG export includes the observation
summary and comparisons. Mobile charts show fewer comparison bars while keeping
the selected region visible.
The map keeps the national view while highlighting the selected province.
It stays mounted through tab changes, exports, and request retry.

User monitoring defaults to the latest source snapshot inside the queried period
(not a claim of live readings), with a 550–600px desktop map and all 3-hour trend
points from the last seven source days. Open the calendar to inspect another
month or date/time range. Native queries remain within the 31-day limit;
daily or monthly resolution can show a full year.
AQI is selectable when supplied; a
historical period without AQI never inherits the latest snapshot AQI. Snapshot
pollutants without fields stay unavailable. The six primary pollutant cards and
the User metric selector include NO₂, SO₂, CO and O₃. When only total-column gas
data is supplied, they use the corresponding `*Column` fields with explicit
“tổng cột” labels and source units (`mg/m²`); these values are never assigned to
surface-concentration fields. Gas snapshots share the same timestamp as PM,
and missing values remain unavailable. Gas selection updates the map values,
trend, comparisons, observation table and CSV export. The source does not identify a
dominant pollutant or provide an update timestamp separate from its data period.

Admin defaults to the last seven source days, with five compact KPIs and a
desktop map that fills the height of the adjacent time-series/ranking column.
Below 1024px, the map occupies its own row; charts share a row on tablets and
stack on phones. Map height is 440px on tablets and 350px on phones, with
Leaflet resizing alongside its container. The initial national overview refits
when its container changes size; a view manually panned/zoomed by the user
keeps its center and zoom. Fractional zoom avoids clipping the national extent
on short phone maps. Advanced panels
appear one at a time in accessible tabs. Province ranking uses the selected
metric, including its year-over-year KPI. The priority table retains its PM2.5-specific columns and supports search,
sorting and internal scrolling; emission details also scroll internally.
Sector filtering applies to emission panels, while province/period applies to
all panels. Weather/column metrics remain available on Admin when supported.

AQI uses six shared levels with a custom green → yellow-green → yellow → orange → red → deep red display palette across its map, tooltip, summary and KPI. The light-theme text uses darker companion colors.
Concentration maps use four saturated colors (green → yellow → orange → deep red) and source-supplied cutoffs. These colors indicate increasing values, not AQI categories.
Without cutoffs, available values use a single neutral gray-blue fill and tooltip values;
no thresholds or AQI are inferred. Data quality counts finite values in received
records, not absent upstream observations or station availability. Annual
exceedance totals are shown only for a complete year selection and are never
prorated. The QCVN panel awaits source thresholds, averaging intervals and the
applicable standard version before claiming compliance.

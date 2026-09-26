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

`/user` loads its data from `GET /api/dashboard` once per page session. `/admin`
loads its management view from `GET /api/admin/dashboard` through the same Vite
API proxy.
The request is shared across React StrictMode mounts; filter/map interactions
use the same in-memory response without additional API requests. The dashboard
layout and local GeoJSON map render independently of that request. While it is
pending, data cards, chart, comparison and emissions show animated skeletons
(respecting reduced-motion preferences). A failed request leaves static
placeholders and an inline error with a retry button; it never replaces the
whole dashboard. The request has a 15-second timeout.

Province/sector selectors and exports remain unavailable until their data is
ready. Map exploration and other filters stay usable. Retrying preserves the
map instance, zoom, local highlight and filter choices; recovered readings
update the existing map layers. Successful empty responses use the normal
empty-data UI, not error/loading placeholders. There is no local mock fallback.
Reload the page to fetch a fresh snapshot after a successful load.

Vite dev and preview proxy `/api` to `http://127.0.0.1:8000`. To override it,
copy `.env.example` to `.env.local`, change `API_PROXY_TARGET`, and restart Vite.
Production output is `dist/app/`, so builds preserve `dist/.gitkeep`. Deploy
that directory and configure your web server to reverse-proxy `/api/*` to
FastAPI, preserving the prefix.

## Structure

- `src/main.tsx`: React entry point and global stylesheet import.
- `src/App.tsx`: application-level route selection for `/user` and `/admin`.
- `src/pages/user/UserDashboard.tsx`: user dashboard composition and derived values.
- `src/pages/admin/AdminDashboard.tsx`: management dashboard presentation and filters.
- `src/components/dashboard/`: dashboard controls, comparison, loading/error states, and exports.
- `src/components/ui/`: reusable buttons and form controls.
- `src/features/analytics/`: interactive trend chart.
- `src/features/geography/`: map layers and province-data loading.
- `src/services/dashboardApi.ts`: shared HTTP request to the backend.
- `src/hooks/useDashboardData.ts`: request lifecycle, loading/error state, and retry.
- `src/services/adminDashboardApi.ts` and `src/hooks/useAdminDashboardData.ts`: Admin API request lifecycle, loading/error state, and retry.
- `../backend/data/samples/`: current temporary CAMS sample, served by the API; not validated Gold data.
- `../backend/app/repositories/mock/dashboard.py`: older five-province demo, enabled only with `DASHBOARD_DATA_SOURCE=mock`.
- `src/types/dashboard.ts`: shared dashboard data types.
- `public/data/`: prepared map GeoJSON served as static assets.
- `public/favicon.svg`: application icon.

Directories containing `.gitkeep` are intentional placeholders and are retained. The Vite, TypeScript, ESLint, and npm lock files support development and reproducible builds.

## Styling

Use Tailwind utility classes in React components. The Vite integration follows the [official Tailwind setup](https://tailwindcss.com/docs/installation/using-vite).

- `src/index.css` is the single stylesheet entry: Tailwind imports, theme tokens, and Leaflet's vendor stylesheet. Do not add component stylesheets or custom selector rules.
- Theme tokens use `@theme`, for example `bg-surface`, `text-accent`, `border-border`, `rounded-card`, and `shadow-card`.
- `src/components/ui/Button.tsx` provides buttons and segmented controls. `FormControls.tsx` provides labeled fields, selects, and date inputs. These include focus, disabled, and reduced-motion states.
- Keep conditional utility names complete so Tailwind can detect them at build time. Use `aria-pressed` for segmented control selection.
- Leaflet's vendor stylesheet is imported into the `components` layer so Tailwind utilities can override it. Map controls and tooltips use Tailwind descendant variants. Leaflet still handles geographic geometry, positioning, and dynamic path styles; those styles reference the same `--color-*` theme tokens.
- The trend chart retains SVG presentation attributes so exported SVG files work independently of the dashboard stylesheet.

## Province map boundaries

The map reads `public/data/vietnam-provinces.geojson`, a standalone frontend asset containing all 34 province boundaries from `../data/landing/reference/vietnamese-provinces-database/json/geojson/` (dataset `v5.1.0`). Every source coordinate and MultiPolygon ring is preserved, including islands and holes. Only province identifiers, names, area, and geometry are bundled; ward data is not needed.

The GeoJSON is committed and served directly by Vite. Building or deploying `frontend` alone does not require the reference directory or a data-generation script.

Clicking a province draws its geometry in a separate, non-interactive highlight layer above the map. Provinces without air-quality readings can also be highlighted; only provinces with readings update the dashboard filters. Changing a province filter resets the map selection. Keyboard focus follows the province outline, and Enter/Space selects it.

## World basemap

`WorldBasemap.tsx` draws a muted gray, non-interactive vector background from `public/data/world-countries.geojson`. It contains country outlines only: no roads, place labels, satellite images, or provincial boundaries outside Vietnam. Vietnam is excluded from the background and drawn exclusively from the existing detailed province asset above it.

The background source is [Natural Earth Admin 0 at 1:110m](https://www.naturalearthdata.com/downloads/110m-cultural-vectors/110m-admin-0-countries/), pinned to the `v5.1.2` repository release. Natural Earth data is [public domain](https://www.naturalearthdata.com/about/terms-of-use/). Its coarse Vietnam outline differs from the province dataset, so using it directly would leave gaps and overlaps along the land border.

The committed world asset already contains the corrected border arcs of China, Laos, and Cambodia, using matching coordinates from the union of Vietnam's province geometries. Shared three-country junctions use identical connectors. The province geometry remains at its original resolution, while the rest of the background stays coarse. Leaflet uses `smoothFactor: 0` on both layers so it does not simplify their shared coordinates differently when zooming.

The frontend consumes these prepared GeoJSON files directly; there is no generation step or Python/GIS dependency. When replacing map data in the future, update the two assets together and verify that the shared borders still match.

The generated asset has 176 country features and 23,839 positions, about 504 KiB uncompressed (172 KiB gzipped). The background is fetched once from the app's own origin and cached in memory. Its geometry stays mounted across province filters and metric changes. Panning and zooming make no additional background requests. Loading runs independently of province data; a failed background request leaves the province layer and dashboard controls available. The background pane sits below province boundaries and does not receive pointer events.

Local Chromium validation covered one background request across filter changes, pan and zoom; absence of image tiles and external map requests; gray country styling; province keyboard selection; widths down to 320px; and slow/failed background loading. With 4x CPU throttling, three runs before and after border alignment measured a pan/zoom frame interval at the 95th percentile of about 17 ms. Province rendering was ready in approximately 0.60–0.62 s in both versions; the maximum observed frame interval increased from 50 ms to 67 ms. These are local measurements, not a guarantee for every device.

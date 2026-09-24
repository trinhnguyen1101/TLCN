# Air Quality dashboard

React, TypeScript, Vite, Tailwind CSS 4, and React Leaflet.

## Development

```sh
npm ci
npm run dev
```

```sh
npm run lint
npm run build
npm run preview
```

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

To refresh the asset from the local reference dataset:

```sh
npm run sync:provinces
```

The script checks province coverage, unique codes, coordinates, and closed rings before writing the asset. The generated file is committed so building or deploying `frontend` alone does not require the reference directory.

Clicking a province draws its geometry in a separate, non-interactive highlight layer above the map. Provinces without air-quality readings can also be highlighted; only provinces with readings update the dashboard filters. Changing a province filter resets the map selection. Keyboard focus follows the province outline, and Enter/Space selects it.

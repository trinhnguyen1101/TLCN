# Vietnam Administrative Divisions / Việt Nam

Open dataset of Vietnam's administrative hierarchy under the post-2025 restructure (Decision 19/2025/QĐ-TTg). Vietnam eliminated the district level nationwide effective 1 July 2025, creating a streamlined 2-level structure: 34 provincial units directly administering 3,321 communes/wards. This repository provides structured, bilingual (Vietnamese + English) reference data with geographic coordinates at every level. Designed for developers, researchers, government agencies, and AI agents.

Licensed under CC-BY-4.0. Browse the hierarchy through GitHub's folder navigation, download aggregate files in JSON/CSV/NDJSON, or integrate directly via raw URLs.

## Overview

| Item | Details |
|------|---------|
| Province/City | 34 |
| Commune/Ward | 3,321 |
| Coordinates | ✅ Included (all levels) |
| Formats | JSON, NDJSON, CSV |
| License | CC-BY-4.0 |
| Last Updated | 2026-09-08 |
| Website | [openadmindata.org/vn](https://openadmindata.org/vn/) |
| API | [openadmindata.org/api/vn](https://openadmindata.org/api/vn/) |
| Flag | [PNG](https://onlygames.me/flags-png/vn/) · [CDN](https://www.freeflags.org/cdn/) · [CSS](https://www.freeflags.org/css/) · [Collections](https://www.freeflags.org/collections/) |
| National Anthem | [🎵 Listen & Download Vietnam National Anthem MP3](https://onlygames.me/national-anthems/vn/) |
| Statistics | [GDP](https://nationdata.org/gdp/country/vnm) · [Population](https://nationdata.org/population/country/vnm) — via [NationData.org](https://nationdata.org) |

## Browse by Province/City

| # | Province/City | Commune/Wards | Link |
|---|----|----|------|
| 1 | Hà Nội (Hanoi) | 126 | [Browse](divisions/ha-noi-01/) |
| 2 | Cao Bằng (Cao Bang) | 56 | [Browse](divisions/cao-bang-04/) |
| 3 | Tuyên Quang (Tuyen Quang) | 124 | [Browse](divisions/tuyen-quang-08/) |
| 4 | Điện Biên (Dien Bien) | 45 | [Browse](divisions/dien-bien-11/) |
| 5 | Lai Châu (Lai Chau) | 38 | [Browse](divisions/lai-chau-12/) |
| 6 | Sơn La (Son La) | 75 | [Browse](divisions/son-la-14/) |
| 7 | Lào Cai (Lao Cai) | 99 | [Browse](divisions/lao-cai-15/) |
| 8 | Thái Nguyên (Thai Nguyen) | 92 | [Browse](divisions/thai-nguyen-19/) |
| 9 | Lạng Sơn (Lang Son) | 65 | [Browse](divisions/lang-son-20/) |
| 10 | Quảng Ninh (Quang Ninh) | 54 | [Browse](divisions/quang-ninh-22/) |
| 11 | Bắc Ninh (Bac Ninh) | 99 | [Browse](divisions/bac-ninh-24/) |
| 12 | Phú Thọ (Phu Tho) | 148 | [Browse](divisions/phu-tho-25/) |
| 13 | Hải Phòng (Hai Phong) | 114 | [Browse](divisions/hai-phong-31/) |
| 14 | Hưng Yên (Hung Yen) | 104 | [Browse](divisions/hung-yen-33/) |
| 15 | Ninh Bình (Ninh Binh) | 129 | [Browse](divisions/ninh-binh-37/) |
| 16 | Thanh Hóa (Thanh Hoa) | 166 | [Browse](divisions/thanh-hoa-38/) |
| 17 | Nghệ An (Nghe An) | 130 | [Browse](divisions/nghe-an-40/) |
| 18 | Hà Tĩnh (Ha Tinh) | 69 | [Browse](divisions/ha-tinh-42/) |
| 19 | Quảng Trị (Quang Tri) | 78 | [Browse](divisions/quang-tri-44/) |
| 20 | Huế (Hue) | 40 | [Browse](divisions/hue-46/) |
| 21 | Đà Nẵng (Da Nang) | 94 | [Browse](divisions/da-nang-48/) |
| 22 | Quảng Ngãi (Quang Ngai) | 96 | [Browse](divisions/quang-ngai-51/) |
| 23 | Gia Lai | 135 | [Browse](divisions/gia-lai-52/) |
| 24 | Khánh Hòa (Khanh Hoa) | 65 | [Browse](divisions/khanh-hoa-56/) |
| 25 | Đắk Lắk (Dak Lak) | 102 | [Browse](divisions/dak-lak-66/) |
| 26 | Lâm Đồng (Lam Dong) | 124 | [Browse](divisions/lam-dong-68/) |
| 27 | Đồng Nai (Dong Nai) | 95 | [Browse](divisions/dong-nai-75/) |
| 28 | Hồ Chí Minh (Ho Chi Minh City) | 168 | [Browse](divisions/ho-chi-minh-79/) |
| 29 | Tây Ninh (Tay Ninh) | 96 | [Browse](divisions/tay-ninh-80/) |
| 30 | Đồng Tháp (Dong Thap) | 102 | [Browse](divisions/dong-thap-82/) |
| 31 | Vĩnh Long (Vinh Long) | 124 | [Browse](divisions/vinh-long-86/) |
| 32 | An Giang | 102 | [Browse](divisions/an-giang-91/) |
| 33 | Cần Thơ (Can Tho) | 103 | [Browse](divisions/can-tho-92/) |
| 34 | Cà Mau (Ca Mau) | 64 | [Browse](divisions/ca-mau-96/) |

## Data Files

| File | Format | Description |
|------|--------|-------------|
| [all-province.json](data/all-province.json) | JSON | All 34 province/city records |
| [all-ward.json](data/all-ward.json) | JSON | All 3,321 commune/ward records |
| [all-flat.json](data/all-flat.json) | JSON | Levels 1-1 flat array |
| [all-flat.ndjson](data/all-flat.ndjson) | NDJSON | Streaming format |
| [all-flat.csv](data/all-flat.csv) | CSV | Spreadsheet format |
| [hierarchy.json](data/hierarchy.json) | JSON | Nested tree |
| [schema.json](data/schema.json) | JSON Schema | Data schema |

## Quick Start

### Python

```python
import json

with open("data/all-province.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for r in data:
    print(f"{r['name']['local']} ({r['name']['en']}) — {r['children_count']['ward']} commune/wards")
```

### JavaScript

```javascript
import { readFileSync } from "fs";

const data = JSON.parse(readFileSync("data/all-province.json", "utf-8"));
console.log(`Total: ${data.length} province/citys`);
```

## Schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier |
| `level` | integer | 1=province/city, 2=commune/ward |
| `level_name` | object | Level label (local + English) |
| `name.local` | string | Name in local script |
| `name.en` | string | English name |
| `name.slug` | string | URL-safe slug |
| `parent` | object/null | Parent division reference |
| `ancestors` | array | Full ancestor chain |
| `children_count` | object | Count of children per level |
| `zip_codes` | array | Postal codes (where available) |
| `geo.lat` | string | Latitude (WGS84) |
| `geo.lon` | string | Longitude (WGS84) |

Full schema: [data/schema.json](data/schema.json)

## Hierarchy Browse

```
divisions/{province-slug}/
```

Commune/Wards are listed inline in each province/city's README.

## AI Integration

- [llms.txt](docs/llms.txt) — Quick reference for AI agents
- [llms-full.txt](docs/llms-full.txt) — Summary with per-province/city links
- [Per-province/city data](docs/llms-full/) — Full data by province/city

## Citation

```
Vietnam Administrative Divisions Dataset (CC-BY-4.0)
URL: https://github.com/open-admin-data/vietnam-administrative-divisions
```

See [CITATION.cff](CITATION.cff) for machine-readable citation.

## License

- **Data**: [CC-BY-4.0](LICENSE)

## Related

- [Open Admin Data](https://openadmindata.org) — Browse, search and explore administrative divisions for every country
- [open-admin-data](https://github.com/open-admin-data) — GitHub organization with all country repos
- [ListBase](https://www.listbase.org) — Structured reference data for every country
- [FreeFlags.org](https://www.freeflags.org) — Free flag images for every country
- [Flag CDN](https://www.freeflags.org/cdn/) — Hotlink flag images directly
- [Flag CSS](https://www.freeflags.org/css/) — CSS flag sprites for web projects
- [Flag Collections](https://www.freeflags.org/collections/) — Curated flag image packs

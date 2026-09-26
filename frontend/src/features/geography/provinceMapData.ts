interface ProvinceGeoJsonProperties {
  code: string
  name: string
  nameEn: string
  fullName: string
  fullNameEn: string
  codeName: string
  areaKm2: number
}

interface ProvinceGeoJsonFeature {
  type: 'Feature'
  id: string
  properties: ProvinceGeoJsonProperties
  geometry: {
    type: 'MultiPolygon'
    coordinates: number[][][][]
  }
}

export interface ProvinceFeatureCollection {
  type: 'FeatureCollection'
  features: ProvinceGeoJsonFeature[]
}

/** URL served from public/data; load this once in the map page or map service. */
const VIETNAM_PROVINCES_GEOJSON_URL = `${import.meta.env.BASE_URL}data/vietnam-provinces.geojson`

let provinceDataRequest: Promise<ProvinceFeatureCollection> | undefined

export function loadVietnamProvinceMapData(): Promise<ProvinceFeatureCollection> {
  provinceDataRequest ??= fetch(VIETNAM_PROVINCES_GEOJSON_URL)
    .then(async (response) => {
      if (!response.ok) throw new Error('Không thể tải ranh giới tỉnh/thành cho bản đồ.')
      return await response.json() as ProvinceFeatureCollection
    })
    .catch((error: unknown) => {
      provinceDataRequest = undefined
      throw error
    })
  return provinceDataRequest
}

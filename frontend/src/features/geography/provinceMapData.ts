import type { ProvinceSnapshot } from '../../types/dashboard'

export interface ProvinceGeoJsonProperties {
  code: string
  name: string
  nameEn: string
  fullName: string
  fullNameEn: string
  codeName: string
  areaKm2: number
}

export interface ProvinceGeoJsonFeature {
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

export interface ProvinceMapDatum {
  feature: ProvinceGeoJsonFeature
  metrics: ProvinceSnapshot | null
}

/** URL served from public/data; load this once in the map page or map service. */
export const VIETNAM_PROVINCES_GEOJSON_URL = '/data/vietnam-provinces.geojson'

export async function loadVietnamProvinceMapData(
  snapshots: ProvinceSnapshot[],
): Promise<ProvinceMapDatum[]> {
  const response = await fetch(VIETNAM_PROVINCES_GEOJSON_URL)
  if (!response.ok) {
    throw new Error('Không thể tải ranh giới tỉnh/thành cho bản đồ.')
  }

  const geoJson = (await response.json()) as ProvinceFeatureCollection
  const snapshotByProvince = new Map<string, ProvinceSnapshot>(
    snapshots.map((snapshot) => [snapshot.provinceCode, snapshot]),
  )

  return geoJson.features.map((feature) => ({
    feature,
    metrics: snapshotByProvince.get(feature.id) ?? null,
  }))
}

import { useEffect, useMemo, useState } from 'react'
import { GeoJSON, MapContainer } from 'react-leaflet'
import type { PathOptions } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { provinceSnapshots } from '../../services/mockDashboardData'
import type { ProvinceSnapshot } from '../../types/dashboard'
import {
  loadVietnamProvinceMapData,
  type ProvinceFeatureCollection,
} from './provinceMapData'
import './VietnamProvinceMap.css'

type MapMetric = 'aqi' | 'pm25'

interface VietnamProvinceMapProps {
  onProvinceSelect?: (province: ProvinceSnapshot) => void
}

const getAqiColor = (aqi: number) => {
  if (aqi <= 50) return '#22c55e'
  if (aqi <= 100) return '#eab308'
  if (aqi <= 150) return '#f97316'
  return '#dc2626'
}

const getPm25Color = (pm25: number) => {
  if (pm25 <= 15) return '#22c55e'
  if (pm25 <= 25) return '#eab308'
  if (pm25 <= 35) return '#f97316'
  return '#dc2626'
}

function getProvinceStyle(metrics: ProvinceSnapshot | undefined, metric: MapMetric): PathOptions {
  if (!metrics) {
    return { color: '#94a3b8', fillColor: '#e2e8f0', fillOpacity: 0.65, weight: 1 }
  }

  const fillColor = metric === 'aqi' ? getAqiColor(metrics.aqi) : getPm25Color(metrics.pm25)
  return { color: '#ffffff', fillColor, fillOpacity: 0.82, weight: 1.2 }
}

export function VietnamProvinceMap({ onProvinceSelect }: VietnamProvinceMapProps) {
  const [geoJson, setGeoJson] = useState<ProvinceFeatureCollection | null>(null)
  const [metric, setMetric] = useState<MapMetric>('aqi')
  const [error, setError] = useState<string | null>(null)

  const metricsByProvince = useMemo(
    () => new Map<string, ProvinceSnapshot>(provinceSnapshots.map((item) => [item.provinceCode, item])),
    [],
  )

  useEffect(() => {
    let isMounted = true
    loadVietnamProvinceMapData(provinceSnapshots)
      .then((data) => {
        if (isMounted) setGeoJson({ type: 'FeatureCollection', features: data.map(({ feature }) => feature) })
      })
      .catch(() => {
        if (isMounted) setError('Không thể tải dữ liệu ranh giới tỉnh/thành.')
      })
    return () => { isMounted = false }
  }, [])

  if (error) return <p className="map-message map-message--error">{error}</p>
  if (!geoJson) return <p className="map-message">Đang tải bản đồ Việt Nam…</p>

  return (
    <section className="vietnam-map" aria-label="Bản đồ chất lượng không khí Việt Nam">
      <div className="map-toolbar">
        <div>
          <p className="map-eyebrow">Bản đồ theo tỉnh/thành</p>
          <h2>Chất lượng không khí Việt Nam</h2>
        </div>
        <div className="metric-switch" role="group" aria-label="Chỉ số hiển thị trên bản đồ">
          <button className={metric === 'aqi' ? 'is-active' : ''} type="button" onClick={() => setMetric('aqi')}>AQI</button>
          <button className={metric === 'pm25' ? 'is-active' : ''} type="button" onClick={() => setMetric('pm25')}>PM2.5</button>
        </div>
      </div>

      <MapContainer center={[16.2, 107.7]} zoom={5.35} scrollWheelZoom className="leaflet-map">
        <GeoJSON
          key={metric}
          data={geoJson}
          style={(feature) => getProvinceStyle(metricsByProvince.get(String(feature?.id)), metric)}
          onEachFeature={(feature, layer) => {
            const metrics = metricsByProvince.get(String(feature.id))
            const provinceName = feature.properties.name as string
            const tooltip = metrics
              ? `<strong>${provinceName}</strong><br/>AQI: ${metrics.aqi} · ${metrics.status}<br/>PM2.5: ${metrics.pm25} µg/m³<br/><small>Click để xem chi tiết</small>`
              : `<strong>${provinceName}</strong><br/>Chưa có dữ liệu demo`
            layer.bindTooltip(tooltip, { sticky: true })
            layer.on('click', () => { if (metrics) onProvinceSelect?.(metrics) })
          }}
        />
      </MapContainer>

      <div className="map-legend" aria-label="Chú giải màu">
        <span><i className="legend-dot legend-dot--good" />Tốt</span>
        <span><i className="legend-dot legend-dot--moderate" />Trung bình</span>
        <span><i className="legend-dot legend-dot--poor" />Kém</span>
        <span><i className="legend-dot legend-dot--bad" />Xấu</span>
        <span><i className="legend-dot legend-dot--empty" />Chưa có dữ liệu</span>
      </div>
    </section>
  )
}

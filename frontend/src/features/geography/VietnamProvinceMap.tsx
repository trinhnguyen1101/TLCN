import { useEffect, useMemo, useState } from 'react'
import { GeoJSON, MapContainer } from 'react-leaflet'
import type { PathOptions } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { DataState } from '../../components/dashboard/DataState'
import { provinceSnapshots } from '../../services/mockDashboardData'
import type { ProvinceCode, ProvinceSnapshot } from '../../types/dashboard'
import { loadVietnamProvinceMapData, type ProvinceFeatureCollection } from './provinceMapData'
import './VietnamProvinceMap.css'

export type MapMetric = 'aqi' | 'pm25' | 'pm10'

interface VietnamProvinceMapProps {
  selectedProvinceCode?: ProvinceCode | 'all'
  metric?: MapMetric
  layerVisible?: boolean
  onProvinceSelect?: (province: ProvinceSnapshot) => void
  onMetricChange?: (metric: MapMetric) => void
  onLayerVisibilityChange?: (visible: boolean) => void
}

const getMetricColor = (value: number, metric: MapMetric) => {
  if (metric === 'aqi') {
    if (value <= 50) return '#22c55e'
    if (value <= 100) return '#eab308'
    if (value <= 150) return '#f97316'
    return '#dc2626'
  }
  const limits = metric === 'pm25' ? [15, 25, 35] : [30, 50, 75]
  if (value <= limits[0]) return '#22c55e'
  if (value <= limits[1]) return '#eab308'
  if (value <= limits[2]) return '#f97316'
  return '#dc2626'
}

function getProvinceStyle(metrics: ProvinceSnapshot | undefined, metric: MapMetric, layerVisible: boolean, selected: boolean): PathOptions {
  if (!metrics || !layerVisible) {
    return { color: selected ? '#0f766e' : '#94a3b8', fillColor: '#e2e8f0', fillOpacity: layerVisible ? .65 : .18, weight: selected ? 3 : 1 }
  }
  const value = metric === 'aqi' ? metrics.aqi : metrics[metric]
  return { color: selected ? '#0f172a' : '#ffffff', fillColor: getMetricColor(value, metric), fillOpacity: .82, weight: selected ? 3 : 1.2 }
}

export function VietnamProvinceMap({
  selectedProvinceCode = 'all',
  metric = 'aqi',
  layerVisible = true,
  onProvinceSelect,
  onMetricChange,
  onLayerVisibilityChange,
}: VietnamProvinceMapProps) {
  const [geoJson, setGeoJson] = useState<ProvinceFeatureCollection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const metricsByProvince = useMemo(() => new Map<string, ProvinceSnapshot>(provinceSnapshots.map((item) => [item.provinceCode, item])), [])

  useEffect(() => {
    let isMounted = true
    loadVietnamProvinceMapData(provinceSnapshots)
      .then((data) => { if (isMounted) setGeoJson({ type: 'FeatureCollection', features: data.map(({ feature }) => feature) }) })
      .catch(() => { if (isMounted) setError('Không thể tải dữ liệu ranh giới tỉnh/thành.') })
    return () => { isMounted = false }
  }, [])

  return (
    <section className="vietnam-map" aria-label="Bản đồ chất lượng không khí Việt Nam">
      <div className="map-toolbar">
        <div>
          <p className="map-eyebrow">Cross-filter theo tỉnh/thành</p>
          <h2>Bản đồ chất lượng không khí</h2>
        </div>
        <div className="map-controls">
          <div className="metric-switch" role="group" aria-label="Chỉ số hiển thị trên bản đồ">
            {(['aqi', 'pm25', 'pm10'] as MapMetric[]).map((option) => (
              <button key={option} className={metric === option ? 'is-active' : ''} type="button" onClick={() => onMetricChange?.(option)}>{option === 'aqi' ? 'AQI' : option.toUpperCase().replace('25', '2.5')}</button>
            ))}
          </div>
          <button className="layer-toggle" type="button" aria-pressed={layerVisible} onClick={() => onLayerVisibilityChange?.(!layerVisible)}>
            {layerVisible ? 'Ẩn layer' : 'Hiện layer'}
          </button>
        </div>
      </div>

      <DataState loading={!geoJson && !error} error={error}>
        {geoJson && (
          <MapContainer center={[16.2, 107.7]} zoom={5.35} scrollWheelZoom className="leaflet-map">
            <GeoJSON
              key={`${metric}-${layerVisible}-${selectedProvinceCode}`}
              data={geoJson}
              style={(feature) => getProvinceStyle(metricsByProvince.get(String(feature?.id)), metric, layerVisible, String(feature?.id) === selectedProvinceCode)}
              onEachFeature={(feature, layer) => {
                const metrics = metricsByProvince.get(String(feature.id))
                const provinceName = feature.properties.name as string
                const tooltip = metrics
                  ? `<strong>${provinceName}</strong><br/>AQI: ${metrics.aqi} · ${metrics.status}<br/>PM2.5: ${metrics.pm25} µg/m³<br/>PM10: ${metrics.pm10} µg/m³<br/><small>Click để lọc dashboard</small>`
                  : `<strong>${provinceName}</strong><br/>Chưa có dữ liệu demo`
                layer.bindTooltip(tooltip, { sticky: true })
                layer.on('click', () => { if (metrics) onProvinceSelect?.(metrics) })
              }}
            />
          </MapContainer>
        )}
      </DataState>

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

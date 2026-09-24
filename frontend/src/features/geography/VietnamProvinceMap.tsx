import { useEffect, useMemo, useState } from 'react'
import { MapContainer, Pane } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { DataState } from '../../components/dashboard/DataState'
import { DashboardIcon } from '../../components/dashboard/DashboardIcon'
import { provinceSnapshots } from '../../services/mockDashboardData'
import type { ProvinceCode, ProvinceSnapshot } from '../../types/dashboard'
import { loadVietnamProvinceMapData, type ProvinceFeatureCollection } from './provinceMapData'
import { ProvinceBoundaryLayer } from './ProvinceBoundaryLayer'
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
          <h2>Bản đồ chất lượng không khí</h2>
        </div>
        <div className="map-controls">
          <div className="metric-switch" role="group" aria-label="Chỉ số hiển thị trên bản đồ">
            {(['aqi', 'pm25', 'pm10'] as MapMetric[]).map((option) => (
              <button key={option} className={metric === option ? 'is-active' : ''} type="button" aria-pressed={metric === option} onClick={() => onMetricChange?.(option)}>{option === 'aqi' ? 'AQI' : option.toUpperCase().replace('25', '2.5')}</button>
            ))}
          </div>
          <button className="layer-toggle" type="button" aria-pressed={layerVisible} onClick={() => onLayerVisibilityChange?.(!layerVisible)}>
            <DashboardIcon name="layers" />{layerVisible ? 'Ẩn lớp dữ liệu' : 'Hiện lớp dữ liệu'}
          </button>
        </div>
      </div>

      <DataState loading={!geoJson && !error} error={error}>
        {geoJson && (
          <MapContainer center={[16.2, 107.7]} zoom={5.35} scrollWheelZoom className="leaflet-map">
            <Pane name="province-selection" style={{ zIndex: 450, pointerEvents: 'none' }} />
            <ProvinceBoundaryLayer
              key={selectedProvinceCode}
              data={geoJson}
              selectedProvinceCode={selectedProvinceCode}
              metric={metric}
              layerVisible={layerVisible}
              metricsByProvince={metricsByProvince}
              onProvinceSelect={onProvinceSelect}
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

import { useEffect, useMemo, useState } from 'react'
import { MapContainer, Pane, useMap } from 'react-leaflet'
import { DataState } from '../../components/dashboard/DataState'
import { DashboardIcon } from '../../components/dashboard/DashboardIcon'
import { Button, SegmentedControl } from '../../components/ui/Button'
import type { DashboardMetadata, ProvinceCode, ProvinceSnapshot } from '../../types/dashboard'
import { loadVietnamProvinceMapData, type ProvinceFeatureCollection } from './provinceMapData'
import { ProvinceBoundaryLayer } from './ProvinceBoundaryLayer'
import { WorldBasemap } from './WorldBasemap'

import { getMapColorScale, MAP_METRIC_LABELS, type MapMetric } from './mapColorScale'
export type { MapMetric } from './mapColorScale'

interface VietnamProvinceMapProps {
  provinceSnapshots: ProvinceSnapshot[]
  metricMetadata?: DashboardMetadata['metrics']
  selectedProvinceCode?: ProvinceCode | 'all'
  metric?: MapMetric
  layerVisible?: boolean
  onProvinceSelect?: (province: ProvinceSnapshot) => void
  onMetricChange?: (metric: MapMetric) => void
  onLayerVisibilityChange?: (visible: boolean) => void
}

// Leaflet creates these controls outside React; Tailwind descendant variants theme them.
const mapClasses = [
  'w-full min-h-[470px] flex-1 border-t border-border bg-map-background font-sans',
  'motion-reduce:[&_*]:transition-none motion-reduce:[&_*]:animate-none',
  'max-[1100px]:h-[500px] max-[1100px]:flex-none max-[680px]:h-[460px] max-[680px]:min-h-[460px]',
  '[&_.leaflet-control-zoom]:overflow-hidden [&_.leaflet-control-zoom]:rounded-lg [&_.leaflet-control-zoom]:border [&_.leaflet-control-zoom]:border-border-strong [&_.leaflet-control-zoom]:shadow-[0_2px_8px_rgb(0_0_0/24%)]',
  '[&_.leaflet-control-zoom_a]:bg-surface [&_.leaflet-control-zoom_a]:text-[19px] [&_.leaflet-control-zoom_a]:font-normal [&_.leaflet-control-zoom_a]:text-secondary',
  '[&_.leaflet-control-zoom_a:hover]:bg-surface-subtle [&_.leaflet-control-zoom_a:hover]:text-accent',
  '[&_.leaflet-control-zoom_a:focus-visible]:outline-3 [&_.leaflet-control-zoom_a:focus-visible]:outline-offset-[-3px] [&_.leaflet-control-zoom_a:focus-visible]:outline-accent',
  '[&_.leaflet-control-zoom_a.leaflet-disabled]:bg-surface-subtle [&_.leaflet-control-zoom_a.leaflet-disabled]:text-muted [&_.leaflet-control-zoom_a.leaflet-disabled]:opacity-45',
  '[&_.leaflet-control-zoom-in]:border-b-border',
].join(' ')

// Dashboard placeholders and responsive columns can change the map's size
// without a window resize. Keep Leaflet's viewport aligned with its container.
function MapSizeSync() {
  const map = useMap()

  useEffect(() => {
    let frame = 0
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => map.invalidateSize({ animate: false }))
    })
    observer.observe(map.getContainer())
    return () => {
      observer.disconnect()
      cancelAnimationFrame(frame)
    }
  }, [map])

  return null
}

export function VietnamProvinceMap({
  provinceSnapshots,
  metricMetadata,
  selectedProvinceCode = 'all',
  metric = 'pm25',
  layerVisible = true,
  onProvinceSelect,
  onMetricChange,
  onLayerVisibilityChange,
}: VietnamProvinceMapProps) {
  const [geoJson, setGeoJson] = useState<ProvinceFeatureCollection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const metricsByProvince = useMemo(() => new Map<string, ProvinceSnapshot>(provinceSnapshots.map((item) => [item.provinceCode, item])), [provinceSnapshots])

  const concentrationScale = metric === 'aqi' ? undefined : metricMetadata?.[metric]?.mapScale
  const colorScale = getMapColorScale(metric, concentrationScale)

  useEffect(() => {
    let isMounted = true
    loadVietnamProvinceMapData()
      .then((data) => { if (isMounted) setGeoJson(data) })
      .catch(() => { if (isMounted) setError('Không thể tải dữ liệu ranh giới tỉnh/thành.') })
    return () => { isMounted = false }
  }, [])

  return (
    <section className="isolate flex min-w-0 flex-col overflow-hidden rounded-card border border-border bg-surface shadow-card row-span-2 max-[1100px]:row-span-1" aria-label="Bản đồ chất lượng không khí Việt Nam">
      <div className="flex flex-col gap-[18px] p-6 max-[1100px]:flex-row max-[1100px]:flex-wrap max-[1100px]:items-center max-[1100px]:justify-between max-[680px]:gap-4 max-[680px]:p-5">
        <div>
          <h2 className="text-[.98rem] font-semibold text-heading">Bản đồ chất lượng không khí</h2>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 max-[1100px]:justify-start max-[680px]:w-full">
          <SegmentedControl aria-label="Chỉ số hiển thị trên bản đồ">
            {(['aqi', 'pm1', 'pm25', 'pm10'] as MapMetric[]).map((option) => (
              <Button key={option} variant="segment" disabled={!provinceSnapshots.some((province) => typeof province[option] === 'number' && Number.isFinite(province[option]))} aria-pressed={metric === option} onClick={() => onMetricChange?.(option)}>{MAP_METRIC_LABELS[option]}</Button>
            ))}
          </SegmentedControl>
          <Button aria-pressed={layerVisible} onClick={() => onLayerVisibilityChange?.(!layerVisible)}>
            <DashboardIcon name="layers" size="small" />{layerVisible ? 'Ẩn lớp dữ liệu' : 'Hiện lớp dữ liệu'}
          </Button>
        </div>
      </div>

      <DataState className="flex-1" loading={!geoJson && !error} error={error}>
        {geoJson && (
          <MapContainer center={[16.2, 107.7]} zoom={5.35} minZoom={0} maxZoom={19} scrollWheelZoom attributionControl={false} className={mapClasses}>
            <MapSizeSync />
            <WorldBasemap />
            <Pane name="province-selection" className="pointer-events-none z-[450]" />
            <ProvinceBoundaryLayer
              key={selectedProvinceCode}
              data={geoJson}
              selectedProvinceCode={selectedProvinceCode}
              metric={metric}
              colorScale={colorScale}
              layerVisible={layerVisible}
              metricsByProvince={metricsByProvince}
              onProvinceSelect={onProvinceSelect}
            />
          </MapContainer>
        )}
      </DataState>

      <div className="flex flex-wrap gap-x-4 gap-y-3 border-t border-border px-6 py-[17px] text-[.72rem] max-[680px]:px-5 max-[680px]:py-4" aria-label="Chú giải màu">
        <p className="basis-full font-medium">{MAP_METRIC_LABELS[metric]}{metric !== 'aqi' && ' (µg/m³)'}</p>
        {colorScale && (
          <div className="grid w-full grid-cols-2 gap-2 min-[480px]:grid-cols-4">
            {colorScale.labels.map((label, index) => (
              <div key={label} className="flex min-w-0 flex-col gap-1.5 rounded-lg border border-border bg-surface-subtle px-2.5 py-2.5">
                <span className="inline-flex items-center gap-1.5 font-medium text-secondary"><i className="inline-block size-2.5 shrink-0 rounded-full" style={{ backgroundColor: colorScale.colors[index] }} />{label}</span>
                <span className="font-semibold tabular-nums" style={{ color: colorScale.colors[index] }}>{colorScale.ranges[index]}{metric !== 'aqi' && ' µg/m³'}</span>
              </div>
            ))}
          </div>
        )}
        <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2 rounded-full border border-map-province-border bg-map-province-fill" />Chưa có dữ liệu</span>
        {metric !== 'aqi' && (
          <p className="basis-full leading-relaxed text-muted">
            {concentrationScale
              ? 'Thang nồng độ cố định, dùng chung cho PM1, PM2.5 và PM10. Các mức là quy ước hiển thị của ứng dụng, không phải phân loại AQI sức khỏe.'
              : 'Chưa có dữ liệu thang nồng độ.'}
          </p>
        )}
      </div>
    </section>
  )
}

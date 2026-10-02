import { memo, useEffect, useMemo, useState } from 'react'
import { MapContainer, Pane, useMap } from 'react-leaflet'
import { DataState } from '../../components/dashboard/DataState'
import { DashboardIcon } from '../../components/dashboard/DashboardIcon'
import { Button } from '../../components/ui/Button'
import type { DashboardMetadata, ProvinceCode, ProvinceSnapshot } from '../../types/dashboard'
import { loadVietnamProvinceMapData, type ProvinceFeatureCollection } from './provinceMapData'
import { ProvinceBoundaryLayer } from './ProvinceBoundaryLayer'
import { WorldBasemap } from './WorldBasemap'

import { METRIC_META } from '../../services/dashboardSelectors'
import { getMapColorScale, MAP_METRIC_LABELS, type MapMetric } from './mapColorScale'
export type { MapMetric } from './mapColorScale'

interface VietnamProvinceMapProps {
  variant?: 'user' | 'admin'
  periodLabel?: string
  provinceSnapshots: ProvinceSnapshot[]
  metricMetadata?: DashboardMetadata['metrics']
  selectedProvinceCode?: ProvinceCode | 'all'
  metric?: MapMetric
  layerVisible?: boolean
  onProvinceSelect?: (province: ProvinceSnapshot) => void
  onLayerVisibilityChange?: (visible: boolean) => void
}

const MIN_MAP_ZOOM = 4.5
const VIETNAM_MAP_CENTER: [number, number] = [16.2, 107.7]

// Leaflet creates these controls outside React; Tailwind descendant variants theme them.
const mapClasses = [
  'w-full border-t border-border bg-map-background font-sans',
  'motion-reduce:[&_*]:transition-none motion-reduce:[&_*]:animate-none',
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
    map.fitBounds([[8.2, 102], [23.5, 112]], { padding: [16, 16], animate: false, maxZoom: 5.8 })
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

function MinZoomWheelGuard() {
  const map = useMap()

  useEffect(() => {
    const container = map.getContainer()
    const centerVietnamAtMinZoom = () => {
      if (map.getZoom() <= MIN_MAP_ZOOM) {
        map.setView(VIETNAM_MAP_CENTER, MIN_MAP_ZOOM, { animate: false })
      }
    }
    const preventScrollAtMinZoom = (event: WheelEvent) => {
      if (event.deltaY > 0 && map.getZoom() <= MIN_MAP_ZOOM) {
        event.preventDefault()
        event.stopImmediatePropagation()
        centerVietnamAtMinZoom()
      }
    }

    map.on('zoomend', centerVietnamAtMinZoom)
    container.addEventListener('wheel', preventScrollAtMinZoom, { capture: true, passive: false })
    centerVietnamAtMinZoom()
    return () => {
      map.off('zoomend', centerVietnamAtMinZoom)
      container.removeEventListener('wheel', preventScrollAtMinZoom, true)
    }
  }, [map])

  return null
}

export const VietnamProvinceMap = memo(function VietnamProvinceMap({
  variant = 'user',
  periodLabel,
  provinceSnapshots,
  metricMetadata,
  selectedProvinceCode = 'all',
  metric = 'pm25',
  layerVisible = true,
  onProvinceSelect,
  onLayerVisibilityChange,
}: VietnamProvinceMapProps) {
  const [geoJson, setGeoJson] = useState<ProvinceFeatureCollection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const metricsByProvince = useMemo(() => new Map<string, ProvinceSnapshot>(provinceSnapshots.map((item) => [item.provinceCode, item])), [provinceSnapshots])

  const concentrationScale = metric === 'aqi' ? undefined : metricMetadata?.[metric]?.mapScale
  const colorScale = useMemo(() => getMapColorScale(metric, concentrationScale), [metric, concentrationScale])
  const unit = metric === 'aqi' ? '' : metricMetadata?.[metric]?.unit ?? METRIC_META[metric].unit

  useEffect(() => {
    let isMounted = true
    loadVietnamProvinceMapData()
      .then((data) => { if (isMounted) setGeoJson(data) })
      .catch(() => { if (isMounted) setError('Không thể tải dữ liệu ranh giới tỉnh/thành.') })
    return () => { isMounted = false }
  }, [])

  return (
    <section className="isolate flex min-w-0 flex-col overflow-hidden rounded-card border border-border bg-surface shadow-card" data-map-variant={variant} aria-label="Bản đồ chất lượng không khí Việt Nam">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-heading">Việt Nam · {MAP_METRIC_LABELS[metric]}</h2>
          <p className="mt-1 text-xs text-muted">{periodLabel ?? 'Chọn một tỉnh để xem chi tiết'}</p>
        </div>
        <Button aria-pressed={layerVisible} onClick={() => onLayerVisibilityChange?.(!layerVisible)}>
          <DashboardIcon name="layers" size="small" />{layerVisible ? 'Ẩn lớp dữ liệu' : 'Hiện lớp dữ liệu'}
        </Button>
      </div>

      <DataState className="flex-1" loading={!geoJson && !error} error={error}>
        {geoJson && (
          <MapContainer center={VIETNAM_MAP_CENTER} zoom={5.35} minZoom={MIN_MAP_ZOOM} maxZoom={19} scrollWheelZoom="center" attributionControl={false} className={`${mapClasses} ${variant === 'user' ? 'h-[550px] min-[1440px]:h-[600px] max-[767px]:h-[450px]' : 'h-[400px] max-[767px]:h-[350px]'}`}>
            <MapSizeSync />
            <MinZoomWheelGuard />
            <WorldBasemap />
            <Pane name="province-selection" className="pointer-events-none z-[450]" />
            <ProvinceBoundaryLayer
              key={selectedProvinceCode}
              data={geoJson}
              selectedProvinceCode={selectedProvinceCode}
              metric={metric}
              metricUnit={unit}
              colorScale={colorScale}
              layerVisible={layerVisible}
              metricsByProvince={metricsByProvince}
              onProvinceSelect={onProvinceSelect}
            />
          </MapContainer>
        )}
      </DataState>

      <div className="flex flex-wrap gap-x-4 gap-y-2 border-t border-border px-4 py-3 text-[.7rem]" aria-label="Chú giải màu">
        <p className="basis-full font-medium text-secondary">{MAP_METRIC_LABELS[metric]} {unit && `(${unit})`}</p>
        {colorScale?.labels.map((label, index) => <span key={label} className="inline-flex items-center gap-1.5 text-muted"><i className="size-2.5 shrink-0 rounded-sm" style={{ backgroundColor: colorScale.colors[index] }} />{label} · {colorScale.ranges[index]}</span>)}
        {!colorScale && <span className="inline-flex items-center gap-1.5 text-muted"><i className="size-2.5 rounded-sm bg-accent" />Có giá trị · chưa có thang nồng độ</span>}
        <span className="inline-flex items-center gap-1.5 text-muted"><i className="size-2.5 shrink-0 rounded-sm border border-map-province-border bg-map-province-fill" />Chưa có dữ liệu</span>
        {metric !== 'aqi' && <p className="basis-full text-muted">{concentrationScale ? 'Thang nồng độ từ nguồn dữ liệu; không phải mức AQI.' : 'Nguồn chưa cung cấp thang nồng độ. Xem giá trị khi trỏ hoặc chọn tỉnh.'}</p>}
      </div>
    </section>
  )
})

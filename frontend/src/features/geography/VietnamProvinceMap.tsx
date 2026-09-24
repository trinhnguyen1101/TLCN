import { useEffect, useMemo, useState } from 'react'
import { MapContainer, Pane } from 'react-leaflet'
import { DataState } from '../../components/dashboard/DataState'
import { DashboardIcon } from '../../components/dashboard/DashboardIcon'
import { Button, SegmentedControl } from '../../components/ui/Button'
import { provinceSnapshots } from '../../services/mockDashboardData'
import type { ProvinceCode, ProvinceSnapshot } from '../../types/dashboard'
import { loadVietnamProvinceMapData, type ProvinceFeatureCollection } from './provinceMapData'
import { ProvinceBoundaryLayer } from './ProvinceBoundaryLayer'

export type MapMetric = 'aqi' | 'pm25' | 'pm10'

interface VietnamProvinceMapProps {
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
  '[&_.leaflet-control-attribution]:bg-surface [&_.leaflet-control-attribution]:text-[10px] [&_.leaflet-control-attribution]:text-muted [&_.leaflet-control-attribution_a]:text-accent',
].join(' ')

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
            {(['aqi', 'pm25', 'pm10'] as MapMetric[]).map((option) => (
              <Button key={option} variant="segment" aria-pressed={metric === option} onClick={() => onMetricChange?.(option)}>{option === 'aqi' ? 'AQI' : option.toUpperCase().replace('25', '2.5')}</Button>
            ))}
          </SegmentedControl>
          <Button aria-pressed={layerVisible} onClick={() => onLayerVisibilityChange?.(!layerVisible)}>
            <DashboardIcon name="layers" size="small" />{layerVisible ? 'Ẩn lớp dữ liệu' : 'Hiện lớp dữ liệu'}
          </Button>
        </div>
      </div>

      <DataState className="flex-1" loading={!geoJson && !error} error={error}>
        {geoJson && (
          <MapContainer center={[16.2, 107.7]} zoom={5.35} scrollWheelZoom className={mapClasses}>
            <Pane name="province-selection" className="pointer-events-none z-[450]" />
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

      <div className="flex flex-wrap gap-x-4 gap-y-3 border-t border-border px-6 py-[17px] text-[.72rem] max-[680px]:px-5 max-[680px]:py-4" aria-label="Chú giải màu">
        <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2 rounded-full bg-aqi-good" />Tốt</span>
        <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2 rounded-full bg-aqi-moderate" />Trung bình</span>
        <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2 rounded-full bg-aqi-poor" />Kém</span>
        <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2 rounded-full bg-aqi-bad" />Xấu</span>
        <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2 rounded-full border border-map-province-border bg-map-province-fill" />Chưa có dữ liệu</span>
      </div>
    </section>
  )
}

import { useState } from 'react'
import { GeoJSON, Tooltip } from 'react-leaflet'
import type { Path, PolylineOptions } from 'leaflet'
import type { ProvinceSnapshot } from '../../types/dashboard'
import type { ProvinceFeatureCollection } from './provinceMapData'
import { concentrationColor, type MapColorScale, type MapMetric } from './mapColorScale'

interface ProvinceBoundaryLayerProps {
  data: ProvinceFeatureCollection
  selectedProvinceCode: string
  metric: MapMetric
  colorScale: MapColorScale | null
  layerVisible: boolean
  metricsByProvince: Map<string, ProvinceSnapshot>
  onProvinceSelect?: (province: ProvinceSnapshot) => void
}

const selectedProvinceStyle: PolylineOptions = {
  color: 'var(--color-accent)', weight: 3, opacity: 1, fill: false,
  lineCap: 'round', lineJoin: 'round', smoothFactor: 0,
}

function getProvinceStyle(metrics: ProvinceSnapshot | undefined, metric: MapMetric, layerVisible: boolean, colorScale: MapColorScale | null): PolylineOptions {
  const fillColor = concentrationColor(metrics?.[metric], colorScale)
  if (!fillColor || !layerVisible) {
    return { color: 'var(--color-map-province-border)', fillColor: 'var(--color-map-province-fill)', fillOpacity: layerVisible ? .65 : .18, weight: 1, smoothFactor: 0, className: 'focus:outline-none focus-visible:stroke-accent focus-visible:stroke-3' }
  }
  return { color: 'var(--color-surface-subtle)', fillColor, fillOpacity: 1, weight: 1.2, smoothFactor: 0, className: 'focus:outline-none focus-visible:stroke-accent focus-visible:stroke-3' }
}

// The parent keys this layer by the dashboard selection so filters reset local selection.
export function ProvinceBoundaryLayer({ data, selectedProvinceCode, metric, colorScale, layerVisible, metricsByProvince, onProvinceSelect }: ProvinceBoundaryLayerProps) {
  const [highlightedCode, setHighlightedCode] = useState(selectedProvinceCode)
  const highlightedFeature = data.features.find((feature) => feature.id === highlightedCode)

  return (
    <>
      {data.features.map((feature) => {
        const metrics = metricsByProvince.get(feature.id)
        const selectProvince = () => {
          setHighlightedCode(feature.id)
          if (metrics) onProvinceSelect?.(metrics)
        }

        return (
          <GeoJSON
            key={feature.id}
            data={feature}
            style={getProvinceStyle(metrics, metric, layerVisible, colorScale)}
            onEachFeature={(_, layer) => {
              layer.on('add', () => {
                const element = (layer as Path).getElement()
                element?.setAttribute('tabindex', '0')
                element?.setAttribute('role', 'button')
                element?.setAttribute('aria-label', feature.properties.fullName)
              })
            }}
            eventHandlers={{
              click: selectProvince,
              keydown: (event) => {
                if (event.originalEvent.key === 'Enter' || event.originalEvent.key === ' ') {
                  event.originalEvent.preventDefault()
                  event.originalEvent.stopPropagation()
                  selectProvince()
                }
              },
            }}
          >
            <Tooltip sticky className="rounded-lg border-border bg-surface px-3.5 py-[11px] font-sans text-[.75rem] leading-[1.9] text-secondary shadow-[0_4px_16px_rgb(0_0_0/32%)] [&.leaflet-tooltip-left]:before:border-l-surface [&.leaflet-tooltip-right]:before:border-r-surface [&.leaflet-tooltip-top]:before:border-t-surface [&.leaflet-tooltip-bottom]:before:border-b-surface">
              <strong className="font-semibold text-heading">{feature.properties.name}</strong><br />
              {metrics ? <>
                AQI: {metrics.aqi ?? 'Chưa có dữ liệu'} {metrics.status ?? ''}<br />
                PM1: {metrics.pm1?.toFixed(1) ?? '—'} µg/m³<br />
                PM2.5: {metrics.pm25?.toFixed(1) ?? '—'} µg/m³<br />
                PM10: {metrics.pm10?.toFixed(1) ?? '—'} µg/m³
              </> : 'Chưa có dữ liệu'}
            </Tooltip>
          </GeoJSON>
        )
      })}
      {highlightedFeature && (
        <GeoJSON
          key={highlightedFeature.id}
          data={highlightedFeature}
          pane="province-selection"
          interactive={false}
          style={selectedProvinceStyle}
        />
      )}
    </>
  )
}
